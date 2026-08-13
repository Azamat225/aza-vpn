from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from aza_vpn.config import parse_env_file
from aza_vpn.errors import ConfigurationError
from aza_vpn.models import Client, ClientState, RealitySecrets, RuntimeSettings
from aza_vpn.xray.generator import render_strict_template, render_xray_config


TEST_UUID = "123e4567-e89b-42d3-a456-426614174000"


def settings_mapping() -> dict[str, str]:
    return {
        "AZA_SERVER_ADDRESS": "203.0.113.10",
        "AZA_SERVER_LABEL": "Germany-01",
        "AZA_VLESS_PORT": "18443",
        "AZA_LISTEN_ADDRESS": "0.0.0.0",
        "REALITY_SERVER_NAME": "www.example.com",
        "REALITY_DEST": "www.example.com:443",
        "REALITY_FINGERPRINT": "chrome",
        "XRAY_VERSION": "latest",
        "XRAY_LOG_LEVEL": "warning",
    }


class ConfigurationTests(unittest.TestCase):
    def test_parse_env_does_not_execute_shell_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "must-not-exist"
            env_file = root / ".env"
            env_file.write_text(
                f"VALUE=$(touch {marker})\nQUOTED='hello world'\n", encoding="utf-8"
            )
            parsed = parse_env_file(env_file)
            self.assertTrue(parsed["VALUE"].startswith("$(touch"))
            self.assertEqual(parsed["QUOTED"], "hello world")
            self.assertFalse(marker.exists())

    def test_runtime_settings_reject_privileged_port(self) -> None:
        values = settings_mapping()
        values["AZA_VLESS_PORT"] = "443"
        with self.assertRaisesRegex(ConfigurationError, "without root"):
            RuntimeSettings.from_mapping(values)

    def test_xray_config_uses_reality_target_raw_and_all_clients(self) -> None:
        root = Path(__file__).resolve().parents[1]
        settings = RuntimeSettings.from_mapping(settings_mapping())
        secrets = RealitySecrets(
            private_key="A" * 43,
            client_key="B" * 43,
            short_id="a1b2c3d4e5f60708",
            created_at="2026-01-01T00:00:00+00:00",
        )
        state = ClientState(
            clients={
                "azamat": Client("azamat", TEST_UUID, "2026-01-01T00:00:00+00:00")
            }
        )
        rendered = render_xray_config(
            root / "templates/xray/config.json.j2", settings, secrets, state
        )
        parsed = json.loads(rendered)

        inbound = parsed["inbounds"][0]
        self.assertEqual(inbound["port"], 18443)
        self.assertEqual(inbound["streamSettings"]["network"], "raw")
        reality = inbound["streamSettings"]["realitySettings"]
        self.assertEqual(reality["target"], "www.example.com:443")
        self.assertNotIn("dest", reality)
        self.assertEqual(reality["privateKey"], "A" * 43)
        self.assertNotIn("B" * 43, rendered)
        self.assertEqual(
            inbound["settings"]["clients"],
            [{"email": "azamat", "flow": "xtls-rprx-vision", "id": TEST_UUID}],
        )
        self.assertEqual(parsed["outbounds"], [{"tag": "direct", "protocol": "freedom"}])

    def test_strict_renderer_refuses_unaccounted_values(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "unused"):
            render_strict_template('{"x": {{ value }}}', {"value": 1, "unexpected": 2})


if __name__ == "__main__":
    unittest.main()
