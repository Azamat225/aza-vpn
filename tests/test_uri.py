from __future__ import annotations

import unittest
from urllib.parse import parse_qs, unquote, urlsplit

from aza_vpn.clients.uri import VlessUri


TEST_UUID = "123e4567-e89b-42d3-a456-426614174000"
TEST_PUBLIC_KEY = "B" * 43


class VlessUriTests(unittest.TestCase):
    def test_contains_only_required_client_fields_and_encodes_label(self) -> None:
        uri = VlessUri(
            uuid=TEST_UUID,
            address="203.0.113.10",
            port=18443,
            server_name="www.example.com",
            public_key=TEST_PUBLIC_KEY,
            short_id="a1b2c3d4e5f60708",
            fingerprint="chrome",
            label="Germany 01 / azamat #1",
        ).build()

        parsed = urlsplit(uri)
        self.assertEqual(parsed.scheme, "vless")
        self.assertEqual(parsed.username, TEST_UUID)
        self.assertEqual(parsed.hostname, "203.0.113.10")
        self.assertEqual(parsed.port, 18443)
        self.assertEqual(unquote(parsed.fragment), "Germany 01 / azamat #1")
        self.assertEqual(
            parse_qs(parsed.query),
            {
                "encryption": ["none"],
                "flow": ["xtls-rprx-vision"],
                "security": ["reality"],
                "sni": ["www.example.com"],
                "fp": ["chrome"],
                "pbk": [TEST_PUBLIC_KEY],
                "sid": ["a1b2c3d4e5f60708"],
                "type": ["tcp"],
            },
        )
        self.assertNotIn("private", uri.lower())
        self.assertNotIn("/etc/", uri)

    def test_brackets_ipv6_address(self) -> None:
        uri = VlessUri(
            uuid=TEST_UUID,
            address="2001:db8::10",
            port=8443,
            server_name="example.com",
            public_key=TEST_PUBLIC_KEY,
            short_id="0011",
            fingerprint="chrome",
            label="ipv6",
        ).build()
        self.assertIn("@[2001:db8::10]:8443?", uri)


if __name__ == "__main__":
    unittest.main()
