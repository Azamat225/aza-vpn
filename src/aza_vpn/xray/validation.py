"""Native Xray config validation and rollback-aware atomic activation."""

from __future__ import annotations

from pathlib import Path

from aza_vpn.errors import ServiceError, XrayError
from aza_vpn.utils.files import atomic_replace, replace_backup
from aza_vpn.utils.shell import restart_systemd_service, run_command


def _redact(text: str, values: tuple[str, ...]) -> str:
    redacted = text
    for value in values:
        if value:
            redacted = redacted.replace(value, "[REDACTED]")
    return redacted


def validate_xray_config(
    xray_binary: Path,
    config_file: Path,
    *,
    redactions: tuple[str, ...] = (),
) -> str:
    if not xray_binary.is_file():
        raise XrayError(f"Dedicated Xray binary does not exist: {xray_binary}")
    if not config_file.is_file():
        raise XrayError(f"Xray config does not exist: {config_file}")
    result = run_command(
        [str(xray_binary), "run", "-test", "-config", str(config_file)],
        timeout=30,
    )
    output = _redact("\n".join(part for part in (result.stdout, result.stderr) if part), redactions)
    if result.returncode != 0:
        summary = output.splitlines()[-1] if output else "no diagnostic output"
        raise XrayError(f"Xray rejected the candidate config: {summary}")
    return output or "valid"


class ConfigApplier:
    def __init__(self, xray_binary: Path, config_file: Path, service_name: str) -> None:
        self.xray_binary = xray_binary
        self.config_file = config_file
        self.service_name = service_name

    @property
    def backup_file(self) -> Path:
        return self.config_file.with_name(f"{self.config_file.name}.bak")

    def apply(
        self,
        candidate: Path,
        *,
        restart: bool,
        redactions: tuple[str, ...] = (),
    ) -> None:
        try:
            validate_xray_config(
                self.xray_binary,
                candidate,
                redactions=redactions,
            )
        except Exception:
            candidate.unlink(missing_ok=True)
            raise

        had_previous = self.config_file.exists()
        if had_previous:
            replace_backup(self.config_file, self.backup_file, mode=0o640)
        try:
            atomic_replace(candidate, self.config_file)
        except Exception as exc:
            candidate.unlink(missing_ok=True)
            raise XrayError(f"Cannot activate the validated Xray config: {exc}") from exc

        if not restart:
            return
        try:
            restart_systemd_service(self.service_name)
        except ServiceError as restart_error:
            rollback_error: Exception | None = None
            try:
                if had_previous and self.backup_file.exists():
                    atomic_replace(self.backup_file, self.config_file)
                    restart_systemd_service(self.service_name)
                else:
                    self.config_file.unlink(missing_ok=True)
            except Exception as exc:  # best effort after the original restart failure
                rollback_error = exc
            if rollback_error is not None:
                raise ServiceError(
                    f"New config failed and rollback also failed: {restart_error}; {rollback_error}"
                ) from restart_error
            raise ServiceError(
                f"New config failed; the previous config was restored: {restart_error}"
            ) from restart_error
