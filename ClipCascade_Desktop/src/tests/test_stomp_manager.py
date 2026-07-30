"""Unit tests for STOMPManager's reconnect-path re-authentication (task 9.3).

Run from ClipCascade_Desktop/src/:
    python3 -m unittest tests.test_stomp_manager -v
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stomp_ws.stomp_manager import STOMPManager, _is_rejected_session


class TestIsRejectedSession(unittest.TestCase):
    def test_login_redirect_scheme_error_is_rejected(self):
        self.assertTrue(_is_rejected_session("scheme http is invalid"))

    def test_login_path_in_error_is_rejected(self):
        self.assertTrue(_is_rejected_session("redirected to http://host/login"))

    def test_connection_refused_is_not_rejected(self):
        self.assertFalse(_is_rejected_session("[Errno 61] Connection refused"))

    def test_timeout_is_not_rejected(self):
        self.assertFalse(_is_rejected_session("Connection to ws://host timed out"))

    def test_none_is_not_rejected(self):
        self.assertFalse(_is_rejected_session(None))


class TestReconnectReauthentication(unittest.TestCase):
    """Task 9.3: the reconnect path re-authenticates only on a rejected
    session (redirect to login), not on a plain unreachable server, and a
    refused re-authentication still falls through to a reconnect attempt."""

    def setUp(self):
        self.manager = STOMPManager.__new__(STOMPManager)
        self.manager.config = MagicMock()
        self.manager.config.data = {"cookie": "stale-cookie"}
        self.manager.is_login_phase = False
        self.manager.disconnected = False
        self.manager.first_conn_lost = True
        self.manager.is_auto_reconnecting = False
        self.manager.notification_manager = MagicMock()
        self.manager.request_manager = MagicMock()
        self.manager.connect = MagicMock(return_value=(True, "ok"))
        self.manager.client = MagicMock()

    def test_rejected_session_reauthenticates_once_then_reconnects(self):
        self.manager.client.last_error = "scheme http is invalid"
        self.manager.request_manager.login.return_value = (True, "", {"JSESSIONID": "new"})
        with patch("stomp_ws.stomp_manager.time.sleep"):
            self.manager._on_close()
        self.manager.request_manager.login.assert_called_once()
        self.assertEqual(self.manager.config.data["cookie"], {"JSESSIONID": "new"})
        self.manager.connect.assert_called_once()

    def test_unreachable_server_reconnects_without_login(self):
        self.manager.client.last_error = "[Errno 61] Connection refused"
        with patch("stomp_ws.stomp_manager.time.sleep"):
            self.manager._on_close()
        self.manager.request_manager.login.assert_not_called()
        self.manager.connect.assert_called_once()

    def test_refused_reauthentication_falls_through_to_reconnect(self):
        self.manager.client.last_error = "scheme http is invalid"
        self.manager.request_manager.login.return_value = (False, "bad credentials", None)
        with patch("stomp_ws.stomp_manager.time.sleep"):
            self.manager._on_close()
        self.manager.request_manager.login.assert_called_once()
        self.assertEqual(self.manager.config.data["cookie"], "stale-cookie")
        self.manager.connect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
