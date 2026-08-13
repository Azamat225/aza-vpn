"""Use Xray's own cryptographic commands; no key agreement is implemented here."""

from __future__ import annotations

from pathlib import Path
import re
import secrets
from typing import NamedTuple

from aza_vpn.errors import StateError, XrayError
from aza_vpn.models import (
    RealitySecrets,
    utc_now,
    validate_key,
    validate_short_id,
    validate_uuid,
)
from aza_vpn.utils.shell import run_command


KEY_LINE_RE = re.compile(
    r"^[ \t]*(?P<label>[A-Za-z][A-Za-z0-9]*(?:[ \t]+[A-Za-z][A-Za-z0-9]*)*)"
    r"[ \t]*:[ \t]*(?P<value>\S*)[ \t]*$"
)
ALLOWED_X25519_LABELS = {"privatekey", "publickey", "password", "hash32"}
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)


class RealityKeyPair(NamedTuple):
    """Server-only private key plus the key material required by clients."""

    private_key: str
    client_key: str


def _x25519_format_error(detail: str) -> XrayError:
    return XrayError(
        f"Xray x25519 returned an invalid or unknown format ({detail}); "
        "refusing to guess."
    )


def parse_x25519_output(output: str) -> RealityKeyPair:
    """Parse only known Xray output schemas and deliberately discard Hash32.

    Xray has named the client-side value ``Public key``, ``PublicKey``, and most
    recently ``Password``.  Matching is case-insensitive and ignores whitespace
    inside labels, but every non-empty output line must still be a known field.
    """

    fields: dict[str, str] = {}
    saw_line = False
    for line in output.splitlines():
        if not line.strip():
            continue
        saw_line = True
        match = KEY_LINE_RE.fullmatch(line)
        if match is None:
            raise _x25519_format_error("malformed line")
        label = re.sub(r"[ \t]+", "", match.group("label")).lower()
        value = match.group("value")
        if label not in ALLOWED_X25519_LABELS:
            raise _x25519_format_error("unexpected field")
        if not value:
            raise _x25519_format_error(f"empty {label} field")
        previous = fields.get(label)
        if previous is not None and previous != value:
            raise _x25519_format_error(f"conflicting duplicate {label} field")
        fields[label] = value

    if not saw_line or "privatekey" not in fields:
        raise _x25519_format_error("missing private key")
    public_key = fields.get("publickey")
    password = fields.get("password")
    if public_key is None and password is None:
        raise _x25519_format_error("missing client key")
    if public_key is not None and password is not None and public_key != password:
        raise _x25519_format_error("conflicting client key fields")
    if "hash32" in fields and password is None:
        raise _x25519_format_error("Hash32 without Password")

    client_key = password if password is not None else public_key
    assert client_key is not None
    try:
        private_key = validate_key(fields["privatekey"], "Reality private key")
        client_key = validate_key(client_key, "Reality client key")
    except StateError as exc:
        raise _x25519_format_error("invalid key encoding") from exc
    return RealityKeyPair(private_key=private_key, client_key=client_key)


def generate_reality_secrets(xray_binary: Path) -> RealitySecrets:
    result = run_command([str(xray_binary), "x25519"], timeout=15)
    if result.returncode != 0:
        raise XrayError("Xray failed to generate the Reality X25519 key pair.")
    key_pair = parse_x25519_output(f"{result.stdout}\n{result.stderr}")
    short_id = validate_short_id(secrets.token_hex(8))
    return RealitySecrets(
        private_key=key_pair.private_key,
        client_key=key_pair.client_key,
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
