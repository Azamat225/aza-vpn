from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aza_vpn.errors import ServiceError, XrayError
from aza_vpn.utils.shell import CommandResult
from aza_vpn.xray.validation import (
    ConfigApplier,
    candidate_path_for,
    validate_xray_config,
)


class ConfigValidationTests(unittest.TestCase):
    def test_validator_uses_explicit_json_argv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xray = root / "xray"
            xray.write_text("placeholder", encoding="utf-8")
            candidate = root / "config.candidate.json"
            candidate.write_text("{}", encoding="utf-8")
            with patch(
                "aza_vpn.xray.validation.run_command",
                return_value=CommandResult(0, "", ""),
            ) as run:
                self.assertEqual(validate_xray_config(xray, candidate), "valid")
            self.assertEqual(
                run.call_args.args[0],
                [str(xray), "run", "-test", "-format=json", "-c", str(candidate)],
            )

    def test_candidate_path_is_same_directory_and_ends_in_json(self) -> None:
        active = Path("/etc/aza-vpn/config.json")
        candidate = candidate_path_for(active)
        self.assertEqual(candidate.parent, active.parent)
        self.assertEqual(candidate.name, "config.candidate.json")
        self.assertEqual(candidate.suffix, ".json")
        self.assertNotIn(".new", candidate.name)

    def test_invalid_candidate_is_cleaned_without_replacing_production_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xray = root / "xray"
            xray.write_text("placeholder", encoding="utf-8")
            active = root / "config.json"
            active.write_text("old-config", encoding="utf-8")
            candidate = candidate_path_for(active)
            candidate.write_text("invalid-config", encoding="utf-8")

            with patch(
                "aza_vpn.xray.validation.validate_xray_config",
                side_effect=XrayError("invalid JSON"),
            ):
                applier = ConfigApplier(xray, active, "aza-xray.service")
                with self.assertRaisesRegex(XrayError, "invalid JSON"):
                    applier.apply(candidate, restart=False)

            self.assertEqual(active.read_text(encoding="utf-8"), "old-config")
            self.assertFalse(candidate.exists())

    def test_valid_candidate_atomically_replaces_production_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xray = root / "xray"
            xray.write_text("placeholder", encoding="utf-8")
            active = root / "config.json"
            active.write_text("old-config", encoding="utf-8")
            candidate = candidate_path_for(active)
            candidate.write_text("new-config", encoding="utf-8")

            with patch("aza_vpn.xray.validation.validate_xray_config", return_value="valid"):
                ConfigApplier(xray, active, "aza-xray.service").apply(candidate, restart=False)

            self.assertEqual(active.read_text(encoding="utf-8"), "new-config")
            self.assertFalse(candidate.exists())
            self.assertEqual(
                active.with_name("config.json.bak").read_text(encoding="utf-8"),
                "old-config",
            )

    def test_restart_failure_restores_previous_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xray = root / "xray"
            xray.write_text("placeholder", encoding="utf-8")
            active = root / "config.json"
            active.write_text("old-config", encoding="utf-8")
            candidate = candidate_path_for(active)
            candidate.write_text("new-config", encoding="utf-8")
            calls = 0

            def restart(_: str) -> None:
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise ServiceError("simulated failure")

            with (
                patch("aza_vpn.xray.validation.validate_xray_config", return_value="valid"),
                patch("aza_vpn.xray.validation.restart_systemd_service", side_effect=restart),
            ):
                applier = ConfigApplier(xray, active, "aza-xray.service")
                with self.assertRaisesRegex(ServiceError, "previous config was restored"):
                    applier.apply(candidate, restart=True)
            self.assertEqual(active.read_text(encoding="utf-8"), "old-config")
            self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
