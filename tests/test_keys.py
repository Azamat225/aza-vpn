from __future__ import annotations

import unittest

from aza_vpn.errors import XrayError
from aza_vpn.xray.keys import RealityKeyPair, parse_x25519_output


PRIVATE = "A" * 43
CLIENT = "B" * 43
OTHER = "C" * 43


class KeyParserTests(unittest.TestCase):
    def assert_pair(self, output: str) -> None:
        self.assertEqual(
            parse_x25519_output(output),
            RealityKeyPair(private_key=PRIVATE, client_key=CLIENT),
        )

    def test_parse_old_spaced_labels(self) -> None:
        self.assert_pair(f"Private key: {PRIVATE}\nPublic key: {CLIENT}")

    def test_parse_camel_case_labels(self) -> None:
        self.assert_pair(f"PrivateKey: {PRIVATE}\nPublicKey: {CLIENT}")

    def test_client_credential_label_variants_are_equivalent(self) -> None:
        for label in ("Public key", "PublicKey", "Password", "Password (PublicKey)"):
            with self.subTest(label=label):
                self.assert_pair(f"PrivateKey: {PRIVATE}\n{label}: {CLIENT}")

    def test_parse_current_password_public_key_alias_and_hash32_output(self) -> None:
        self.assert_pair(
            f"PrivateKey: {PRIVATE}\nPassword (PublicKey): {CLIENT}\nHash32: {OTHER}"
        )

    def test_parse_crlf_case_and_whitespace_variations(self) -> None:
        self.assert_pair(
            f"\tprivate KEY \t:  {PRIVATE}\r\n"
            f" password ( publickey ) :\t{CLIENT}  \r\n"
            f" hash32: {OTHER}\r\n"
        )

    def test_password_alias_duplicate_with_same_value_is_allowed(self) -> None:
        self.assert_pair(
            f"PrivateKey: {PRIVATE}\nPassword: {CLIENT}\n"
            f"Password (PublicKey): {CLIENT}\nHash32: {OTHER}"
        )

    def test_hash32_is_never_selected_as_client_key(self) -> None:
        pair = parse_x25519_output(
            f"PrivateKey: {PRIVATE}\nPassword: {CLIENT}\nHash32: {OTHER}"
        )
        self.assertEqual(pair.client_key, CLIENT)
        self.assertNotEqual(pair.client_key, OTHER)

    def test_missing_private_is_rejected(self) -> None:
        with self.assertRaisesRegex(XrayError, "missing private key"):
            parse_x25519_output(f"Password: {CLIENT}\nHash32: {OTHER}")

    def test_missing_client_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(XrayError, "missing client key"):
            parse_x25519_output(f"PrivateKey: {PRIVATE}")

    def test_malformed_or_unknown_output_is_rejected(self) -> None:
        invalid_outputs = (
            "some future output",
            f"PrivateKey: {PRIVATE}\nPassword: {CLIENT}\nWarning: unexpected",
            f"PrivateKey={PRIVATE}\nPassword: {CLIENT}",
            f"PrivateKey: \nPassword: {CLIENT}",
        )
        for output in invalid_outputs:
            with self.subTest(output=output), self.assertRaises(XrayError):
                parse_x25519_output(output)

    def test_conflicting_duplicate_fields_are_rejected(self) -> None:
        invalid_outputs = (
            f"PrivateKey: {PRIVATE}\nPrivate key: {OTHER}\nPassword: {CLIENT}",
            f"PrivateKey: {PRIVATE}\nPassword: {CLIENT}\nPassword: {OTHER}",
            f"PrivateKey: {PRIVATE}\nPassword: {CLIENT}\n"
            f"Password (PublicKey): {OTHER}",
            f"PrivateKey: {PRIVATE}\nPublicKey: {CLIENT}\nPassword: {OTHER}",
        )
        for output in invalid_outputs:
            with (
                self.subTest(output=output),
                self.assertRaisesRegex(XrayError, "conflicting"),
            ):
                parse_x25519_output(output)

    def test_key_values_are_validated_without_echoing_secrets(self) -> None:
        invalid_private = "private-production-secret"
        with self.assertRaises(XrayError) as context:
            parse_x25519_output(f"PrivateKey: {invalid_private}\nPassword: {CLIENT}")
        self.assertNotIn(invalid_private, str(context.exception))

    def test_parenthetical_aliases_are_restricted_to_password_public_key(self) -> None:
        invalid_outputs = (
            f"PrivateKey (PublicKey): {PRIVATE}\nPassword: {CLIENT}",
            f"PublicKey (Password): {CLIENT}\nPrivateKey: {PRIVATE}",
            f"Password (Hash32): {CLIENT}\nPrivateKey: {PRIVATE}",
        )
        for output in invalid_outputs:
            with self.subTest(output=output), self.assertRaisesRegex(XrayError, "unexpected"):
                parse_x25519_output(output)


if __name__ == "__main__":
    unittest.main()
