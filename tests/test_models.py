from __future__ import annotations

import unittest

from aza_vpn.errors import StateError
from aza_vpn.models import RealitySecrets


class RealitySecretsTests(unittest.TestCase):
    def test_reads_legacy_public_key_state(self) -> None:
        secrets = RealitySecrets.from_dict(
            {
                "private_key": "A" * 43,
                "public_key": "B" * 43,
                "short_id": "0011",
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        )
        self.assertEqual(secrets.client_key, "B" * 43)
        self.assertEqual(secrets.public_key, "B" * 43)

    def test_writes_only_semantic_client_key_and_no_hash32(self) -> None:
        serialized = RealitySecrets(
            private_key="A" * 43,
            client_key="B" * 43,
            short_id="0011",
            created_at="2026-01-01T00:00:00+00:00",
        ).to_dict()
        self.assertEqual(serialized["client_key"], "B" * 43)
        self.assertNotIn("public_key", serialized)
        self.assertNotIn("hash32", serialized)

    def test_conflicting_legacy_and_current_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(StateError, "conflicting"):
            RealitySecrets.from_dict(
                {
                    "private_key": "A" * 43,
                    "client_key": "B" * 43,
                    "public_key": "C" * 43,
                    "short_id": "0011",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            )


if __name__ == "__main__":
    unittest.main()
