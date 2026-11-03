"""Unit tests for STOMPManager's reconnect path: re-authentication (task 9.3)
and the retry loop.

Run from ClipCascade_Desktop/src/:
    python3 -m unittest tests.test_stomp_manager -v
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.constants import RECONNECT_WS_TIMER
from stomp_ws.stomp_manager import STOMPManager, _is_rejected_session


def _make_manager():
    manager = STOMPManager.__new__(STOMPManager)
    manager.config = MagicMock()
    manager.config.data = {"cookie": "stale-cookie"}
    manager.is_login_phase = False
    manager.disconnected = False
    manager.first_conn_lost = True
    manager.is_auto_reconnecting = False
    manager.is_reconnect_loop_running = False
    manager.notification_manager = MagicMock()
    manager.request_manager = MagicMock()
    manager.client = MagicMock()
    return manager


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
        self.manager = _make_manager()
        self.manager.connect = MagicMock(return_value=(True, "ok"))

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


class TestReconnectLoop(unittest.TestCase):
    """A lost connection is retried every RECONNECT_WS_TIMER seconds until
    connect() succeeds or the user disconnects, and only one loop runs."""

    def setUp(self):
        self.manager = _make_manager()
        self.manager.client.last_error = "[Errno 2] No such file or directory"

    def test_retries_until_connect_succeeds(self):
        self.manager.connect = MagicMock(
            side_effect=[(False, "x"), (False, "x"), (True, "ok")]
        )
        with patch("stomp_ws.stomp_manager.time.sleep") as sleep:
            self.manager._on_close()
        self.assertEqual(self.manager.connect.call_count, 3)
        self.assertEqual(sleep.call_count, 3)
        sleep.assert_called_with(RECONNECT_WS_TIMER)
        self.assertFalse(self.manager.is_reconnect_loop_running)

    def test_stops_when_disconnected_during_failing_attempt(self):
        def failing_connect():
            self.manager.disconnected = True
            return False, "x"

        self.manager.connect = MagicMock(side_effect=failing_connect)
        with patch("stomp_ws.stomp_manager.time.sleep"):
            self.manager._on_close()
        self.manager.connect.assert_called_once()
        self.assertFalse(self.manager.is_reconnect_loop_running)

    def test_disconnect_during_wait_makes_no_connect_call(self):
        self.manager.connect = MagicMock(return_value=(True, "ok"))

        def disconnect_during_sleep(_):
            self.manager.disconnected = True

        with patch(
            "stomp_ws.stomp_manager.time.sleep", side_effect=disconnect_during_sleep
        ):
            self.manager._on_close()
        self.manager.connect.assert_not_called()

    def test_close_while_loop_running_returns_at_once(self):
        self.manager.is_reconnect_loop_running = True
        self.manager.connect = MagicMock()
        with patch("stomp_ws.stomp_manager.time.sleep") as sleep:
            self.manager._on_close()
        sleep.assert_not_called()
        self.manager.connect.assert_not_called()
        self.assertTrue(self.manager.is_reconnect_loop_running)

    def test_connection_lost_notification_fires_once_per_outage(self):
        self.manager.connect = MagicMock(
            side_effect=[(False, "x"), (False, "x"), (True, "ok")]
        )
        with patch("stomp_ws.stomp_manager.time.sleep"):
            self.manager._on_close()
        self.assertEqual(self.manager.notification_manager.notify.call_count, 1)


if __name__ == "__main__":
    unittest.main()
