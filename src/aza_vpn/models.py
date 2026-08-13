"""Validated domain models kept independent from the JSON storage backend."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import ipaddress
import re
from typing import Any, Mapping
from uuid import UUID

from aza_vpn.errors import ConfigurationError, StateError


CLIENT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}\.?$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*"
    r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.?$"
)
KEY_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
SHORT_ID_RE = re.compile(r"^(?:[0-9a-fA-F]{2}){1,8}$")
FINGERPRINT_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
LOG_LEVELS = {"debug", "info", "warning", "error", "none"}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def validate_client_name(name: str) -> str:
    if not CLIENT_NAME_RE.fullmatch(name):
        raise StateError(
            "Client name must be 1-64 lowercase ASCII characters and may contain "
            "digits, dots, underscores, or hyphens."
        )
    return name


def validate_uuid(value: str) -> str:
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as exc:
        raise StateError("Client UUID is invalid.") from exc
    if parsed.version != 4:
        raise StateError("Client UUID must be UUIDv4.")
    return str(parsed)


def validate_key(value: str, label: str) -> str:
    if not KEY_RE.fullmatch(value):
        raise StateError(f"{label} is not a valid raw URL-safe X25519 key.")
    return value


def validate_short_id(value: str) -> str:
    if not SHORT_ID_RE.fullmatch(value):
        raise StateError(
            "Reality shortId must contain an even number of hexadecimal characters "
            "(2-16 characters)."
        )
    return value.lower()


def _validate_host(value: str, label: str) -> str:
    candidate = value.strip()
    if not candidate or any(marker in candidate for marker in ("<", ">", "CHANGE_ME")):
        raise ConfigurationError(f"{label} is required and must not be a placeholder.")
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        try:
            ascii_host = candidate.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ConfigurationError(f"{label} is not a valid host name.") from exc
        if not HOSTNAME_RE.fullmatch(ascii_host):
            raise ConfigurationError(f"{label} is not a valid IP address or host name.")
    return candidate


def _validate_server_name(value: str) -> str:
    candidate = _validate_host(value, "REALITY_SERVER_NAME")
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return candidate.rstrip(".")
    raise ConfigurationError("REALITY_SERVER_NAME must be a DNS name accepted by the target certificate.")


def _parse_target(value: str) -> tuple[str, int]:
    candidate = value.strip()
    if candidate.startswith("["):
        closing = candidate.find("]")
        if closing == -1 or closing + 1 >= len(candidate) or candidate[closing + 1] != ":":
            raise ConfigurationError("REALITY_DEST must use [IPv6]:port syntax for IPv6.")
        host, port_text = candidate[1:closing], candidate[closing + 2 :]
    else:
        if candidate.count(":") != 1:
            raise ConfigurationError("REALITY_DEST must use host:port syntax.")
        host, port_text = candidate.rsplit(":", 1)
    host = _validate_host(host, "REALITY_DEST host")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ConfigurationError("REALITY_DEST port must be an integer.") from exc
    if not 1 <= port <= 65535:
        raise ConfigurationError("REALITY_DEST port must be between 1 and 65535.")
    return host, port


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    server_address: str
    server_label: str
    port: int
    listen_address: str
    reality_server_name: str
    reality_dest: str
    reality_fingerprint: str
    xray_version: str
    log_level: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> RuntimeSettings:
        required = (
            "AZA_SERVER_ADDRESS",
            "AZA_SERVER_LABEL",
            "AZA_VLESS_PORT",
            "REALITY_SERVER_NAME",
            "REALITY_DEST",
            "XRAY_VERSION",
        )
        missing = [key for key in required if not values.get(key, "").strip()]
        if missing:
            raise ConfigurationError("Missing required settings: " + ", ".join(missing))

        server_address = _validate_host(values["AZA_SERVER_ADDRESS"], "AZA_SERVER_ADDRESS")
        label = values["AZA_SERVER_LABEL"].strip()
        if not 1 <= len(label) <= 80 or not all(char.isprintable() for char in label):
            raise ConfigurationError("AZA_SERVER_LABEL must contain 1-80 printable characters.")
        try:
            port = int(values["AZA_VLESS_PORT"])
        except ValueError as exc:
            raise ConfigurationError("AZA_VLESS_PORT must be an integer.") from exc
        if not 1024 <= port <= 65535:
            raise ConfigurationError(
                "AZA_VLESS_PORT must be between 1024 and 65535 so Xray can run without root."
            )
        listen_address = values.get("AZA_LISTEN_ADDRESS", "0.0.0.0").strip()
        try:
            ipaddress.ip_address(listen_address)
        except ValueError as exc:
            raise ConfigurationError("AZA_LISTEN_ADDRESS must be an IP address.") from exc

        server_name = _validate_server_name(values["REALITY_SERVER_NAME"])
        reality_dest = values["REALITY_DEST"].strip()
        _parse_target(reality_dest)
        fingerprint = values.get("REALITY_FINGERPRINT", "chrome").strip()
        if not FINGERPRINT_RE.fullmatch(fingerprint):
            raise ConfigurationError("REALITY_FINGERPRINT contains unsupported characters.")
        xray_version = values["XRAY_VERSION"].strip()
        if xray_version != "latest" and not re.fullmatch(
            r"v?[0-9]+(?:\.[0-9]+){2}(?:[-.][0-9A-Za-z]+)*", xray_version
        ):
            raise ConfigurationError("XRAY_VERSION must be 'latest' or an explicit release tag.")
        log_level = values.get("XRAY_LOG_LEVEL", "warning").strip().lower()
        if log_level not in LOG_LEVELS:
            raise ConfigurationError("XRAY_LOG_LEVEL must be debug, info, warning, error, or none.")

        return cls(
            server_address=server_address,
            server_label=label,
            port=port,
            listen_address=listen_address,
            reality_server_name=server_name,
            reality_dest=reality_dest,
            reality_fingerprint=fingerprint,
            xray_version=xray_version,
            log_level=log_level,
        )


@dataclass(frozen=True, slots=True)
class Client:
    name: str
    uuid: str
    created_at: str

    def __post_init__(self) -> None:
        validate_client_name(self.name)
        validate_uuid(self.uuid)
        if not self.created_at:
            raise StateError("Client creation timestamp is missing.")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Client:
        try:
            return cls(
                name=str(data["name"]),
                uuid=str(data["uuid"]),
                created_at=str(data["created_at"]),
            )
        except KeyError as exc:
            raise StateError(f"Client state is missing {exc.args[0]!r}.") from exc

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RealitySecrets:
    private_key: str
    public_key: str
    short_id: str
    created_at: str

    def __post_init__(self) -> None:
        validate_key(self.private_key, "Reality private key")
        validate_key(self.public_key, "Reality public key/password")
        validate_short_id(self.short_id)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RealitySecrets:
        try:
            return cls(
                private_key=str(data["private_key"]),
                public_key=str(data["public_key"]),
                short_id=str(data["short_id"]),
                created_at=str(data["created_at"]),
            )
        except KeyError as exc:
            raise StateError(f"Secrets file is missing {exc.args[0]!r}.") from exc

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class ClientState:
    schema_version: int = 1
    clients: dict[str, Client] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ClientState:
        if data.get("schema_version") != 1:
            raise StateError("Unsupported client state schema version.")
        raw_clients = data.get("clients")
        if not isinstance(raw_clients, list):
            raise StateError("Client state must contain a clients list.")
        clients: dict[str, Client] = {}
        for item in raw_clients:
            if not isinstance(item, Mapping):
                raise StateError("Client state contains a malformed record.")
            client = Client.from_dict(item)
            if client.name in clients:
                raise StateError(f"Duplicate client name in state: {client.name}")
            clients[client.name] = client
        return cls(schema_version=1, clients=clients)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "clients": [self.clients[name].to_dict() for name in sorted(self.clients)],
        }
