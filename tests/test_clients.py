from __future__ import annotations

import json
import os
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
from aza_vpn.xray.validation import ConfigApplier


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
            public_key="B" * 43,
            short_id="a1b2c3d4e5f60708",
            created_at="2026-01-01T00:00:00+00:00",
        )
    )


def fake_apply(self: ConfigApplier, candidate: Path, **_: object) -> None:
    os.replace(candidate, self.config_file)


class ClientServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.paths = make_paths(Path(self.temporary.name))
        initialize_repositories(self.paths)

    def test_create_and_remove_regenerate_config_atomically(self) -> None:
        with (
            patch("aza_vpn.clients.service.generate_client_uuid", return_value=UUID_ONE),
            patch.object(ConfigApplier, "apply", fake_apply),
        ):
            service = ClientService(self.paths)
            client = service.create_client("azamat")
            self.assertEqual(client.uuid, UUID_ONE)
            self.assertEqual(service.get_client("azamat"), client)
            self.assertIn("vless://", service.uri_for(client))
            active = json.loads(self.paths.config_file.read_text(encoding="utf-8"))
            self.assertEqual(
                active["inbounds"][0]["settings"]["clients"][0]["email"], "azamat"
            )

            removed = service.remove_client("azamat")
            self.assertEqual(removed, client)
            self.assertEqual(service.list_clients(), [])
            active = json.loads(self.paths.config_file.read_text(encoding="utf-8"))
            self.assertEqual(active["inbounds"][0]["settings"]["clients"], [])

    def test_duplicate_client_is_rejected(self) -> None:
        with (
            patch("aza_vpn.clients.service.generate_client_uuid", return_value=UUID_ONE),
            patch.object(ConfigApplier, "apply", fake_apply),
        ):
            service = ClientService(self.paths)
            service.create_client("azamat")
            with self.assertRaisesRegex(StateError, "already exists"):
                service.create_client("azamat")


if __name__ == "__main__":
    unittest.main()

