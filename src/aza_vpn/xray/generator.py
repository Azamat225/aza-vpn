"""Render the tracked Xray JSON template with JSON-encoded values only."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Mapping

from aza_vpn.errors import ConfigurationError
from aza_vpn.models import ClientState, RealitySecrets, RuntimeSettings


PLACEHOLDER_RE = re.compile(r"{{\s*([a-z][a-z0-9_]*)\s*}}")


def render_strict_template(template: str, values: Mapping[str, Any]) -> str:
    placeholders = set(PLACEHOLDER_RE.findall(template))
    missing = placeholders - values.keys()
    unused = values.keys() - placeholders
    if missing:
        raise ConfigurationError(
            "Xray template is missing values for: " + ", ".join(sorted(missing))
        )
    if unused:
        raise ConfigurationError("Xray renderer has unused values: " + ", ".join(sorted(unused)))

    encoded = {
        key: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        for key, value in values.items()
    }

    def replace(match: re.Match[str]) -> str:
        return encoded[match.group(1)]

    result = PLACEHOLDER_RE.sub(replace, template)
    if "{{" in result or "}}" in result:
        raise ConfigurationError("Xray template contains an unsupported placeholder expression.")
    try:
        parsed = json.loads(result)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Rendered Xray template is invalid JSON: {exc}") from exc
    return json.dumps(parsed, ensure_ascii=False, indent=2) + "\n"


def render_xray_config(
    template_file: Path,
    settings: RuntimeSettings,
    secrets: RealitySecrets,
    state: ClientState,
) -> str:
    try:
        template = template_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(f"Cannot read Xray template {template_file}: {exc}") from exc
    clients = [
        {
            "id": client.uuid,
            "email": client.name,
            "flow": "xtls-rprx-vision",
        }
        for client in (state.clients[name] for name in sorted(state.clients))
    ]
    return render_strict_template(
        template,
        {
            "log_level": settings.log_level,
            "listen_address": settings.listen_address,
            "port": settings.port,
            "clients": clients,
            "reality_target": settings.reality_dest,
            "reality_server_name": settings.reality_server_name,
            "reality_private_key": secrets.private_key,
            "reality_short_id": secrets.short_id,
        },
    )
