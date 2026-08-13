from __future__ import annotations

import unittest

from aza_vpn.errors import XrayError
from aza_vpn.xray.keys import parse_x25519_output


class KeyParserTests(unittest.TestCase):
    def test_parse_current_xray_password_output(self) -> None:
        private, public = parse_x25519_output(
            f"Private key: {'A' * 43}\nPassword: {'B' * 43}\nHash32: ignored"
        )
        self.assertEqual(private, "A" * 43)
        self.assertEqual(public, "B" * 43)

    def test_parse_legacy_xray_public_key_output(self) -> None:
        private, public = parse_x25519_output(
            f"Private key: {'A' * 43}\nPublic key: {'B' * 43}"
        )
        self.assertEqual(private, "A" * 43)
        self.assertEqual(public, "B" * 43)

    def test_unknown_key_output_is_not_guessed(self) -> None:
        with self.assertRaisesRegex(XrayError, "unknown format"):
            parse_x25519_output("some future output")


if __name__ == "__main__":
    unittest.main()

