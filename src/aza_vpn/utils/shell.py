"""Small subprocess boundary; no shell interpolation is used."""

from __future__ import annotations

from dataclasses import dataclass
import shutil
import subprocess
from typing import Sequence

from aza_vpn.errors import ServiceError


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def run_command(args: Sequence[str], timeout: int = 30) -> CommandResult:
    try:
        completed = subprocess.run(
            list(args),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ServiceError(f"Cannot execute {args[0]!r}: {exc}") from exc
    return CommandResult(completed.returncode, completed.stdout.strip(), completed.stderr.strip())


def systemd_state(service_name: str) -> str:
    if shutil.which("systemctl") is None:
        return "unavailable"
    result = run_command(["systemctl", "is-active", service_name], timeout=10)
    return result.stdout or "inactive"


def restart_systemd_service(service_name: str) -> None:
    if shutil.which("systemctl") is None:
        raise ServiceError("systemctl is not available; cannot restart the dedicated Xray service.")
    restart = run_command(["systemctl", "restart", service_name], timeout=30)
    if restart.returncode != 0:
        detail = restart.stderr or restart.stdout or "unknown systemctl error"
        raise ServiceError(f"Restart of {service_name} failed: {detail}")
    active = run_command(["systemctl", "is-active", service_name], timeout=10)
    if active.returncode != 0 or active.stdout != "active":
        raise ServiceError(f"{service_name} did not become active after restart.")
