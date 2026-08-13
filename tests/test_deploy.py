from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DeploymentFlowTests(unittest.TestCase):
    def test_install_has_distinct_incomplete_recovery_path(self) -> None:
        script = (ROOT / "deploy/install.sh").read_text(encoding="utf-8")
        self.assertIn('INSTALL_MODE="recovery"', script)
        self.assertIn("Incomplete managed AZA VPN installation detected", script)
        self.assertIn('[[ -f "$AZA_INSTALL_RECORD" ]]', script)
        self.assertIn("require_aza_marker", script)

    def test_completion_record_is_written_only_after_service_is_active(self) -> None:
        script = (ROOT / "deploy/install.sh").read_text(encoding="utf-8")
        active_check = script.index("systemctl is-active --quiet aza-xray.service")
        record_write = script.index("/usr/local/bin/aza-vpn record-install")
        self.assertGreater(record_write, active_check)

    def test_allowed_occupied_port_must_belong_to_aza(self) -> None:
        script = (ROOT / "deploy/preflight.sh").read_text(encoding="utf-8")
        self.assertIn('aza_service_owns_tcp_port "$AZA_VLESS_PORT"', script)
        self.assertIn("other than the managed AZA service", script)

    def test_update_refuses_incomplete_install(self) -> None:
        script = (ROOT / "deploy/update.sh").read_text(encoding="utf-8")
        self.assertIn('[[ -f "$AZA_INSTALL_RECORD" ]]', script)
        self.assertIn("Resume it with deploy/install.sh", script)


if __name__ == "__main__":
    unittest.main()
