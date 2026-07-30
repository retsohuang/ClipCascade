"""Unit tests for the saved-credential headless-recovery branch in
Application.authenticate_and_connect (tasks 9.1-9.2).

Run from ClipCascade_Desktop/src/:
    python3 -m unittest tests.test_application -v
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.application import Application
from utils.cipher_manager import CipherManager


class TestSavedCredentialLoginWithCipherEnabled(unittest.TestCase):
    """Task 9.2: with cipher_enabled True, a saved-credential re-login must
    reuse the persisted hashed_password cipher key instead of re-deriving it
    from a raw password the client no longer holds."""

    def setUp(self):
        self.app = Application.__new__(Application)
        self.app.config = MagicMock()
        self.app.config.data = {
            "cookie": "stale-cookie",
            "save_password": True,
            "cipher_enabled": True,
            "password": "storeddigest",
            "hashed_password": b"existing-cipher-key",
            "server_mode": "P2S",
            "server_url": "http://127.0.0.1:8080",
        }
        self.app.stomp_manager = MagicMock()
        # First connect (existing-cookie fast path) fails; second connect
        # (after login()) succeeds — driving the saved-credential branch.
        self.app.stomp_manager.connect.side_effect = [
            (False, "invalid cookie"),
            (True, "ok"),
        ]
        self.app.p2p_manager = MagicMock()
        self.app.request_manager = MagicMock()
        self.app.request_manager.login.return_value = (True, "", "new-cookie")
        self.app.request_manager.get_csrf_token.return_value = "csrf"
        self.app.request_manager.get_server_mode.return_value = "P2S"
        self.app.request_manager.maxsize.return_value = 100
        self.app.cipher_manager = MagicMock()

    def test_login_called_with_stored_digest(self):
        self.app.authenticate_and_connect()
        self.app.request_manager.login.assert_called_once()
        self.assertEqual(self.app.config.data["password"], "storeddigest")

    def test_hashed_password_not_re_derived(self):
        self.app.authenticate_and_connect()
        self.app.cipher_manager.hash_password.assert_not_called()
        self.assertEqual(self.app.config.data["hashed_password"], b"existing-cipher-key")


class TestFreshLoginDigestPersistence(unittest.TestCase):
    """Task 9.1: with save_password True, the value persisted to the client
    config's 'password' field is the SHA3-512 hex digest, never the raw
    password — it is hashed in authenticate_and_connect before
    RequestManager.login() sends it."""

    RAW_PASSWORD = "correct horse battery staple"

    def setUp(self):
        self.app = Application.__new__(Application)
        self.app.config = MagicMock()
        self.app.config.data = {
            "cookie": None,
            "save_password": True,
            "cipher_enabled": False,
            "password": "",
            "hashed_password": None,
            "server_mode": "P2S",
            "server_url": "http://127.0.0.1:8080",
        }
        self.app.stomp_manager = MagicMock()
        self.app.stomp_manager.connect.return_value = (True, "ok")
        self.app.p2p_manager = MagicMock()
        self.app.request_manager = MagicMock()
        self.app.request_manager.login.return_value = (True, "", "new-cookie")
        self.app.request_manager.get_csrf_token.return_value = "csrf"
        self.app.request_manager.get_server_mode.return_value = "P2S"
        self.app.request_manager.maxsize.return_value = 100
        self.app.cipher_manager = MagicMock()

    def test_persisted_password_is_sha3_512_digest(self):
        with patch("core.application.LoginForm") as MockLoginForm:
            MockLoginForm.return_value.mainloop.side_effect = (
                lambda: self.app.config.data.__setitem__("password", self.RAW_PASSWORD)
            )
            self.app.authenticate_and_connect()

        expected_digest = CipherManager.string_to_sha3_512_lowercase_hex(self.RAW_PASSWORD)
        self.assertEqual(self.app.config.data["password"], expected_digest)
        self.assertNotEqual(self.app.config.data["password"], self.RAW_PASSWORD)


if __name__ == "__main__":
    unittest.main()
