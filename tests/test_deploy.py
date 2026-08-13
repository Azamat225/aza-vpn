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

    def test_resumed_install_removes_only_the_known_stale_legacy_candidate(self) -> None:
        script = (ROOT / "deploy/install.sh").read_text(encoding="utf-8")
        self.assertIn('LEGACY_CANDIDATE="$AZA_ETC_DIR/config.json.new"', script)
        self.assertIn('[[ "$INSTALL_MODE" == "recovery"', script)
        self.assertIn('rm -f -- "$LEGACY_CANDIDATE"', script)
        self.assertNotIn('rm -f -- "$AZA_ETC_DIR/config.json"', script)

    def test_install_and_update_use_cli_validation_path(self) -> None:
        install = (ROOT / "deploy/install.sh").read_text(encoding="utf-8")
        update = (ROOT / "deploy/update.sh").read_text(encoding="utf-8")
        self.assertIn('/usr/local/bin/aza-vpn init', install)
        self.assertIn('python3 -m aza_vpn.cli init --no-restart', update)
        self.assertIn('AZA_CONFIG_FILE="$STAGE/config.json"', update)

    def test_systemd_preflight_uses_explicit_json_format(self) -> None:
        unit = (ROOT / "deploy/systemd/aza-xray.service").read_text(encoding="utf-8")
        self.assertIn('run -test -format=json -c /etc/aza-vpn/config.json', unit)

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
