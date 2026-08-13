"""Safe parsing of the deployment environment and fixed application paths."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Mapping

from aza_vpn.errors import ConfigurationError
from aza_vpn.models import RuntimeSettings


ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
KNOWN_SETTINGS = {
    "AZA_SERVER_ADDRESS",
    "AZA_SERVER_LABEL",
    "AZA_VLESS_PORT",
    "AZA_LISTEN_ADDRESS",
    "REALITY_SERVER_NAME",
    "REALITY_DEST",
    "REALITY_FINGERPRINT",
    "XRAY_VERSION",
    "XRAY_LOG_LEVEL",
}


@dataclass(frozen=True, slots=True)
class AppPaths:
    env_file: Path
    state_file: Path
    secrets_file: Path
    config_file: Path
    template_file: Path
    xray_binary: Path
    install_file: Path
    lock_file: Path
    service_name: str = "aza-xray.service"

    @classmethod
    def from_environment(cls, env: Mapping[str, str] | None = None) -> AppPaths:
        source = os.environ if env is None else env
        return cls(
            env_file=Path(source.get("AZA_ENV_FILE", "/etc/aza-vpn/aza-vpn.env")),
            state_file=Path(source.get("AZA_STATE_FILE", "/var/lib/aza-vpn/clients.json")),
            secrets_file=Path(source.get("AZA_SECRETS_FILE", "/etc/aza-vpn/secrets.json")),
            config_file=Path(source.get("AZA_CONFIG_FILE", "/etc/aza-vpn/config.json")),
            template_file=Path(
                source.get("AZA_TEMPLATE_FILE", "/opt/aza-vpn/templates/xray/config.json.j2")
            ),
            xray_binary=Path(source.get("AZA_XRAY_BINARY", "/opt/aza-vpn/xray/xray")),
            install_file=Path(source.get("AZA_INSTALL_FILE", "/var/lib/aza-vpn/install.json")),
            lock_file=Path(source.get("AZA_LOCK_FILE", "/var/lib/aza-vpn/aza-vpn.lock")),
        )


def parse_env_file(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Environment file does not exist: {path}") from exc
    except OSError as exc:
        raise ConfigurationError(f"Cannot read environment file {path}: {exc}") from exc

    result: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigurationError(f"Invalid environment line {line_number}: expected KEY=value.")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not ENV_KEY_RE.fullmatch(key):
            raise ConfigurationError(f"Invalid environment key on line {line_number}: {key!r}.")
        if key in result:
            raise ConfigurationError(f"Duplicate environment key on line {line_number}: {key}.")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        elif value.startswith(("'", '"')) or value.endswith(("'", '"')):
            raise ConfigurationError(f"Mismatched quotes on environment line {line_number}.")
        if "\x00" in value or "\n" in value or "\r" in value:
            raise ConfigurationError(
                f"Invalid control character on environment line {line_number}."
            )
        result[key] = value
    return result


def load_settings(paths: AppPaths, environ: Mapping[str, str] | None = None) -> RuntimeSettings:
    values = parse_env_file(paths.env_file)
    overrides = os.environ if environ is None else environ
    for key in KNOWN_SETTINGS:
        if key in overrides:
            values[key] = overrides[key]
    return RuntimeSettings.from_mapping(values)
