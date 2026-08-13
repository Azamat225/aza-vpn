"""Standards-compatible VLESS sharing URI construction."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from urllib.parse import quote, urlencode

from aza_vpn.models import validate_key, validate_short_id, validate_uuid


@dataclass(frozen=True, slots=True)
class VlessUri:
    uuid: str
    address: str
    port: int
    server_name: str
    public_key: str
    short_id: str
    fingerprint: str
    label: str

    def build(self) -> str:
        user_id = validate_uuid(self.uuid)
        validate_key(self.public_key, "Reality public key/password")
        validate_short_id(self.short_id)
        if not 1 <= self.port <= 65535:
            raise ValueError("VLESS URI port must be between 1 and 65535.")
        try:
            is_ipv6 = isinstance(ipaddress.ip_address(self.address), ipaddress.IPv6Address)
        except ValueError:
            is_ipv6 = False
        address = f"[{self.address}]" if is_ipv6 else self.address
        query = urlencode(
            [
                ("encryption", "none"),
                ("flow", "xtls-rprx-vision"),
                ("security", "reality"),
                ("sni", self.server_name),
                ("fp", self.fingerprint),
                ("pbk", self.public_key),
                ("sid", self.short_id),
                # Sharing links conventionally call the RAW TCP transport "tcp".
                ("type", "tcp"),
            ],
            quote_via=quote,
            safe="",
        )
        fragment = quote(self.label, safe="")
        return f"vless://{user_id}@{address}:{self.port}?{query}#{fragment}"

