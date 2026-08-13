"""Transactional client operations coupled to validated Xray config activation."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from aza_vpn.clients.repository import ClientRepository, SecretRepository
from aza_vpn.clients.uri import VlessUri
from aza_vpn.config import AppPaths, load_settings
from aza_vpn.errors import StateError
from aza_vpn.models import Client, ClientState, RealitySecrets, RuntimeSettings, utc_now
from aza_vpn.utils.files import atomic_write_text, exclusive_lock
from aza_vpn.xray.generator import render_xray_config
from aza_vpn.xray.keys import generate_client_uuid, generate_reality_secrets
from aza_vpn.xray.validation import ConfigApplier, validate_xray_config


class ClientService:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self.clients = ClientRepository(paths.state_file)
        self.secrets = SecretRepository(paths.secrets_file)

    def _settings(self) -> RuntimeSettings:
        return load_settings(self.paths)

    def initialize(self, *, restart: bool = False) -> None:
        with exclusive_lock(self.paths.lock_file):
            settings = self._settings()
            if self.paths.secrets_file.exists():
                secrets_value = self.secrets.load()
            else:
                secrets_value = generate_reality_secrets(self.paths.xray_binary)
                self.secrets.save_new(secrets_value)
            state = self.clients.initialize()
            self._apply_state(settings, secrets_value, state, restart=restart)

    def list_clients(self) -> list[Client]:
        state = self.clients.load()
        return [state.clients[name] for name in sorted(state.clients)]

    def get_client(self, name: str) -> Client:
        state = self.clients.load()
        try:
            return state.clients[name]
        except KeyError as exc:
            raise StateError(f"Client does not exist: {name}") from exc

    def create_client(self, name: str) -> Client:
        from aza_vpn.models import validate_client_name

        validate_client_name(name)
        with exclusive_lock(self.paths.lock_file):
            settings = self._settings()
            secrets_value = self.secrets.load()
            old_state = self.clients.load()
            if name in old_state.clients:
                raise StateError(f"Client already exists: {name}")
            client = Client(
                name=name,
                uuid=generate_client_uuid(self.paths.xray_binary),
                created_at=utc_now(),
            )
            new_clients = dict(old_state.clients)
            new_clients[name] = client
            new_state = replace(old_state, clients=new_clients)
            self._commit_state(settings, secrets_value, old_state, new_state)
            return client

    def remove_client(self, name: str) -> Client:
        with exclusive_lock(self.paths.lock_file):
            settings = self._settings()
            secrets_value = self.secrets.load()
            old_state = self.clients.load()
            try:
                removed = old_state.clients[name]
            except KeyError as exc:
                raise StateError(f"Client does not exist: {name}") from exc
            new_clients = dict(old_state.clients)
            del new_clients[name]
            new_state = replace(old_state, clients=new_clients)
            self._commit_state(settings, secrets_value, old_state, new_state)
            return removed

    def uri_for(self, client: Client) -> str:
        settings = self._settings()
        secrets_value = self.secrets.load()
        return VlessUri(
            uuid=client.uuid,
            address=settings.server_address,
            port=settings.port,
            server_name=settings.reality_server_name,
            client_key=secrets_value.client_key,
            short_id=secrets_value.short_id,
            fingerprint=settings.reality_fingerprint,
            label=f"{settings.server_label} - {client.name}",
        ).build()

    def reconcile(self, *, restart: bool = True) -> None:
        with exclusive_lock(self.paths.lock_file):
            self._apply_state(
                self._settings(),
                self.secrets.load(),
                self.clients.load(),
                restart=restart,
            )

    def validate_active(self) -> str:
        secrets_value = self.secrets.load()
        return validate_xray_config(
            self.paths.xray_binary,
            self.paths.config_file,
            redactions=(secrets_value.private_key,),
        )

    def _commit_state(
        self,
        settings: RuntimeSettings,
        secrets_value: RealitySecrets,
        old_state: ClientState,
        new_state: ClientState,
    ) -> None:
        self.clients.save(new_state)
        try:
            self._apply_state(settings, secrets_value, new_state, restart=True)
        except Exception:
            self.clients.save(old_state)
            raise

    def _apply_state(
        self,
        settings: RuntimeSettings,
        secrets_value: RealitySecrets,
        state: ClientState,
        *,
        restart: bool,
    ) -> None:
        rendered = render_xray_config(self.paths.template_file, settings, secrets_value, state)
        candidate = self.paths.config_file.with_name(f"{self.paths.config_file.name}.new")
        atomic_write_text(candidate, rendered, mode=0o640)
        ConfigApplier(
            self.paths.xray_binary,
            self.paths.config_file,
            self.paths.service_name,
        ).apply(candidate, restart=restart, redactions=(secrets_value.private_key,))
