from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from aza_vpn.clients.repository import ClientRepository, SecretRepository
from aza_vpn.clients.service import ClientService
from aza_vpn.config import AppPaths
from aza_vpn.errors import StateError
from aza_vpn.models import RealitySecrets


UUID_ONE = "123e4567-e89b-42d3-a456-426614174000"


def make_paths(tmp_path: Path) -> AppPaths:
    root = Path(__file__).resolve().parents[1]
    env_file = tmp_path / "aza-vpn.env"
    env_file.write_text(
        "\n".join(
            [
                "AZA_SERVER_ADDRESS=203.0.113.10",
                "AZA_SERVER_LABEL=Germany-01",
                "AZA_VLESS_PORT=18443",
                "AZA_LISTEN_ADDRESS=0.0.0.0",
                "REALITY_SERVER_NAME=www.example.com",
                "REALITY_DEST=www.example.com:443",
                "REALITY_FINGERPRINT=chrome",
                "XRAY_VERSION=latest",
                "XRAY_LOG_LEVEL=warning",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    template = tmp_path / "config.json.j2"
    shutil.copyfile(root / "templates/xray/config.json.j2", template)
    return AppPaths(
        env_file=env_file,
        state_file=tmp_path / "clients.json",
        secrets_file=tmp_path / "secrets.json",
        config_file=tmp_path / "config.json",
        template_file=template,
        xray_binary=tmp_path / "xray",
        install_file=tmp_path / "install.json",
        lock_file=tmp_path / "lock",
    )


def initialize_repositories(paths: AppPaths) -> None:
    ClientRepository(paths.state_file).initialize()
    SecretRepository(paths.secrets_file).save_new(
        RealitySecrets(
            private_key="A" * 43,
            client_key="B" * 43,
            short_id="a1b2c3d4e5f60708",
            created_at="2026-01-01T00:00:00+00:00",
        )
    )


class ClientServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.paths = make_paths(Path(self.temporary.name))
        initialize_repositories(self.paths)

    def test_create_and_remove_use_validator_and_json_candidate(self) -> None:
        with (
            patch("aza_vpn.clients.service.generate_client_uuid", return_value=UUID_ONE),
            patch(
                "aza_vpn.xray.validation.validate_xray_config", return_value="valid"
            ) as validate,
            patch("aza_vpn.xray.validation.restart_systemd_service"),
        ):
            service = ClientService(self.paths)
            client = service.create_client("azamat")
            self.assertEqual(client.uuid, UUID_ONE)
            self.assertEqual(service.get_client("azamat"), client)
            self.assertIn("vless://", service.uri_for(client))
            self.assertNotIn("A" * 43, service.uri_for(client))
            active = json.loads(self.paths.config_file.read_text(encoding="utf-8"))
            self.assertEqual(
                active["inbounds"][0]["settings"]["clients"][0]["email"], "azamat"
            )

            self.assertEqual(validate.call_count, 1)
            removed = service.remove_client("azamat")
            self.assertEqual(removed, client)
            self.assertEqual(service.list_clients(), [])
            active = json.loads(self.paths.config_file.read_text(encoding="utf-8"))
            self.assertEqual(active["inbounds"][0]["settings"]["clients"], [])
            self.assertEqual(validate.call_count, 2)
            for call in validate.call_args_list:
                self.assertTrue(call.args[1].name.endswith(".json"))
                self.assertEqual(call.args[1].name, "config.candidate.json")
            self.assertFalse((self.paths.config_file.parent / "config.json.new").exists())

    def test_duplicate_client_is_rejected(self) -> None:
        with (
            patch("aza_vpn.clients.service.generate_client_uuid", return_value=UUID_ONE),
            patch("aza_vpn.xray.validation.validate_xray_config", return_value="valid"),
            patch("aza_vpn.xray.validation.restart_systemd_service"),
        ):
            service = ClientService(self.paths)
            service.create_client("azamat")
            with self.assertRaisesRegex(StateError, "already exists"):
                service.create_client("azamat")

    def test_initialize_uses_validator_for_install_and_resume_paths(self) -> None:
        with (
            patch(
                "aza_vpn.xray.validation.validate_xray_config", return_value="valid"
            ) as validate,
            patch("aza_vpn.xray.validation.restart_systemd_service"),
        ):
            service = ClientService(self.paths)
            service.initialize(restart=True)
            service.initialize(restart=True)
        self.assertEqual(validate.call_count, 2)
        for call in validate.call_args_list:
            self.assertEqual(call.args[1].name, "config.candidate.json")


if __name__ == "__main__":
    unittest.main()
