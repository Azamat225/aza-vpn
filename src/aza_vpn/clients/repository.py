"""JSON repositories; replaceable by a database adapter in a later control plane."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aza_vpn.errors import StateError
from aza_vpn.models import ClientState, RealitySecrets
from aza_vpn.utils.files import atomic_write_json, read_json


class ClientRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> ClientState:
        return ClientState.from_dict(read_json(self.path))

    def initialize(self) -> ClientState:
        if self.path.exists():
            return self.load()
        state = ClientState()
        self.save(state)
        return state

    def save(self, state: ClientState) -> None:
        atomic_write_json(self.path, state.to_dict(), mode=0o600)


class SecretRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> RealitySecrets:
        data: Any = read_json(self.path)
        if not isinstance(data, dict):
            raise StateError("Secrets file must contain a JSON object.")
        return RealitySecrets.from_dict(data)

    def save_new(self, secrets: RealitySecrets) -> None:
        if self.path.exists():
            raise StateError(f"Refusing to overwrite existing Reality secrets: {self.path}")
        atomic_write_json(self.path, secrets.to_dict(), mode=0o600)

