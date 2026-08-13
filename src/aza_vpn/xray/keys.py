"""Use Xray's own cryptographic commands; no key agreement is implemented here."""

from __future__ import annotations

from pathlib import Path
import re
import secrets

from aza_vpn.errors import XrayError
from aza_vpn.models import RealitySecrets, utc_now, validate_short_id, validate_uuid
from aza_vpn.utils.shell import run_command


PRIVATE_RE = re.compile(r"^Private key:\s*(\S+)\s*$", re.MULTILINE | re.IGNORECASE)
PUBLIC_RE = re.compile(r"^(?:Public key|Password):\s*(\S+)\s*$", re.MULTILINE | re.IGNORECASE)
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)


def parse_x25519_output(output: str) -> tuple[str, str]:
    private_match = PRIVATE_RE.search(output)
    public_match = PUBLIC_RE.search(output)
    if private_match is None or public_match is None:
        raise XrayError(
            "Xray x25519 returned an unknown format; refusing to guess Reality key fields."
        )
    return private_match.group(1), public_match.group(1)


def generate_reality_secrets(xray_binary: Path) -> RealitySecrets:
    result = run_command([str(xray_binary), "x25519"], timeout=15)
    if result.returncode != 0:
        raise XrayError("Xray failed to generate the Reality X25519 key pair.")
    private_key, public_key = parse_x25519_output(f"{result.stdout}\n{result.stderr}")
    short_id = validate_short_id(secrets.token_hex(8))
    return RealitySecrets(
        private_key=private_key,
        public_key=public_key,
        short_id=short_id,
        created_at=utc_now(),
    )


def generate_client_uuid(xray_binary: Path) -> str:
    result = run_command([str(xray_binary), "uuid"], timeout=15)
    if result.returncode != 0:
        raise XrayError("Xray failed to generate a client UUID.")
    match = UUID_RE.search(f"{result.stdout}\n{result.stderr}")
    if match is None:
        raise XrayError("Xray uuid returned an unknown format; refusing to guess a credential.")
    return validate_uuid(match.group(0).lower())

