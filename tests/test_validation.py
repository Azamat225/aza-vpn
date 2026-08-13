from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aza_vpn.errors import ServiceError
from aza_vpn.xray.validation import ConfigApplier


class ConfigActivationTests(unittest.TestCase):
    def test_restart_failure_restores_previous_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xray = root / "xray"
            xray.write_text("placeholder", encoding="utf-8")
            active = root / "config.json"
            active.write_text("old-config", encoding="utf-8")
            candidate = root / "config.json.new"
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
