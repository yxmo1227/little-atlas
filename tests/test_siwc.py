"""Offline SIWC security and session tests; every HTTP exchange is mocked."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from dictionary_app import siwc


class MemoryCredentials:
    def __init__(self) -> None:
        self.values: dict[str, dict] = {}

    def write(self, key: str, value: dict) -> None:
        self.values[key] = value.copy()

    def read(self, key: str) -> dict | None:
        value = self.values.get(key)
        return value.copy() if value else None

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


class FakeServer:
    """Drive the callback handler's captured result with no socket or network."""

    authorization_url = ""

    def __init__(self, _address, handler) -> None:
        self.handler = handler
        self.server_port = 1455
        self.timeout = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def handle_request(self) -> None:
        query = parse_qs(urlsplit(self.authorization_url).query)
        cells = dict(zip(self.handler.do_GET.__code__.co_freevars,
                         self.handler.do_GET.__closure__))
        cells["callback"].cell_contents.update({
            "code": "test-authorization-code",
            "state": query["state"][0],
            "client_id": "oaiapp_test-issued",
        })


class SIWCTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vault = MemoryCredentials()
        self.client = siwc.SIWCClient(Path(self.tmp.name), credential_store=self.vault)
        self.discovery = {
            "issuer": siwc.ISSUER,
            "authorization_endpoint": siwc.ISSUER + "/api/accounts/authorize",
            "token_endpoint": siwc.ISSUER + "/api/accounts/oauth/token",
            "jwks_uri": siwc.ISSUER + "/.well-known/jwks.json",
            "revocation_endpoint": siwc.ISSUER + "/api/accounts/oauth/revoke",
        }

    def test_host_id_is_persistent_and_config_has_no_tokens(self) -> None:
        first = self.client._state["host_id"]
        other = siwc.SIWCClient(Path(self.tmp.name), credential_store=self.vault)
        self.assertEqual(other._state["host_id"], first)
        data = (Path(self.tmp.name) / "chatgpt_accounts.json").read_text()
        self.assertNotIn("access_token", data)
        self.assertNotIn("refresh_token", data)

    def test_sign_in_uses_dynamic_client_pkce_and_keeps_tokens_in_vault(self) -> None:
        FakeServer.authorization_url = ""

        def open_browser(url: str) -> bool:
            FakeServer.authorization_url = url
            return True

        def post_token(_url: str, fields: dict, **_kwargs):
            self.assertEqual(fields["client_id"], "oaiapp_test-issued")
            self.assertEqual(fields["redirect_uri"],
                             "http://127.0.0.1:1455/auth/callback")
            self.assertGreaterEqual(len(fields["code_verifier"]), 43)
            return {"scope": siwc.SCOPES, "token_type": "Bearer",
                    "id_token": "id-secret", "access_token": "access-secret",
                    "refresh_token": "refresh-secret", "expires_in": 3600}

        with (patch.object(self.client, "_discovery", return_value=self.discovery),
              patch.object(self.client, "_verify_id_token", return_value={
                  "sub": "account-subject", "email": "person@example.test"}),
              patch.object(siwc, "HTTPServer", FakeServer),
              patch.object(siwc.webbrowser, "open", side_effect=open_browser),
              patch.object(siwc, "_post_form", side_effect=post_token)):
            profile = self.client.sign_in()
        params = parse_qs(urlsplit(FakeServer.authorization_url).query)
        self.assertEqual(params["client_id"], ["dynamic_agent_client"])
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(params["ext_agent_host_id"], [self.client._state["host_id"]])
        self.assertEqual(params["agent_name_hint"], ["Little Atlas"])
        self.assertEqual(profile["client_id"], "oaiapp_test-issued")
        self.assertTrue(self.client.is_signed_in())
        self.assertEqual(self.client.access_token(), "access-secret")
        config = (Path(self.tmp.name) / "chatgpt_accounts.json").read_text()
        for secret in ("id-secret", "access-secret", "refresh-secret"):
            self.assertNotIn(secret, config)

    def test_verified_id_token_checks_signature_audience_and_nonce(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
        public_jwk["kid"] = "test-key"
        now = datetime.now(timezone.utc)
        claims = {"iss": siwc.ISSUER, "aud": "oaiapp_test-issued",
                  "sub": "account-1", "iat": now, "exp": now + timedelta(minutes=10),
                  "nonce": "nonce-a"}
        token = jwt.encode(claims, private_key, algorithm="RS256",
                           headers={"kid": "test-key"})
        with (patch.object(self.client, "_discovery", return_value=self.discovery),
              patch.object(siwc, "_json_request", return_value={"keys": [public_jwk]})):
            self.assertEqual(self.client._verify_id_token(
                token, "oaiapp_test-issued", "nonce-a")["sub"], "account-1")
            with self.assertRaises(siwc.SIWCError):
                self.client._verify_id_token(token, "wrong-client", "nonce-a")
            with self.assertRaises(siwc.SIWCError):
                self.client._verify_id_token(token, "oaiapp_test-issued", "wrong-nonce")

    def _active_session(self) -> str:
        key = siwc._registration_key("oaiapp_test", "subject")
        self.client._state["registrations"][key] = {
            "client_id": "oaiapp_test", "subject": "subject", "email": "a@example.test"}
        self.client._state["active"] = key
        self.client._save_state(self.client._state)
        self.vault.write(key, {"access_token": "old-access", "refresh_token": "old-refresh",
                               "id_token": "old-id", "scope": siwc.SCOPES.split(),
                               "expires_at": 0})
        return key

    def test_refresh_rotates_token_and_sign_out_clears_it(self) -> None:
        key = self._active_session()

        def post_token(_url: str, fields: dict, **kwargs):
            if fields.get("grant_type") == "refresh_token":
                self.assertEqual(fields["client_id"], "oaiapp_test")
                self.assertEqual(fields["resource"], siwc.RESOURCE)
                self.assertNotIn("scope", fields)
                return {"access_token": "new-access", "refresh_token": "new-refresh",
                        "token_type": "Bearer", "expires_in": 3600}
            self.assertEqual(fields["token"], "new-refresh")
            self.assertTrue(kwargs.get("empty_ok"))
            return {}

        with (patch.object(self.client, "_discovery", return_value=self.discovery),
              patch.object(siwc, "_post_form", side_effect=post_token)):
            self.assertEqual(self.client.access_token(), "new-access")
            self.assertEqual(self.vault.read(key)["refresh_token"], "new-refresh")
            self.client.sign_out()
        self.assertFalse(self.client.is_signed_in())
        self.assertIsNone(self.vault.read(key))
        with self.assertRaises(siwc.SIWCError):
            self.client.access_token()


if __name__ == "__main__":
    unittest.main()
