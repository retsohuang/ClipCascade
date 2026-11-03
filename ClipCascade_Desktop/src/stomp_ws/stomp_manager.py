import json
import logging
import time


from interfaces.ws_interface import WSInterface
from stomp_ws.client import Client
from core.config import Config
from utils.cipher_manager import CipherManager
from clipboard.clipboard_manager import ClipboardManager
from utils.notification_manager import NotificationManager
from utils.request_manager import RequestManager
from utils.ssl_helper import websocket_sslopt_for_config
from core.constants import *

if PLATFORM.startswith(LINUX) and LINUX_USE_CLI_UI:
    from cli.tray import TaskbarPanel
else:
    from gui.tray import TaskbarPanel


def _is_rejected_session(error) -> bool:
    """Classify a lost websocket connection per the design's failure-mode
    table: True when the server answered the upgrade with a redirect to the
    login page (session rejected — re-authenticate), False when there was no
    HTTP response at all (server unreachable — plain retry, unchanged)."""
    if error is None:
        return False
    text = str(error)
    return "scheme http is invalid" in text or "/login" in text


class STOMPManager(WSInterface):
    def __init__(self, config: Config, is_login_phase=True):
        self.config = config
        self.clipboard_manager = ClipboardManager(self.config)
        self.cipher_manager = CipherManager(self.config)
        self.notification_manager = NotificationManager(self.config)
        self.request_manager = RequestManager(self.config)
        self.sys_tray: TaskbarPanel = None
        self.first_conn_lost = True
        self.is_login_phase = is_login_phase
        self.client = None
        self.is_connected = False
        self.disconnected = False
        self.is_auto_reconnecting = False
        self.is_reconnect_loop_running = False

    def set_tray_ref(self, sys_tray: TaskbarPanel):
        """
        Sets the system tray reference.
        """
        self.sys_tray = sys_tray
        self.clipboard_manager.set_tray_ref(sys_tray)

    def get_total_timeout(self):
        """
        Returns the total timeout value in milliseconds."""
        return (RECONNECT_WS_TIMER * 1000) + WEBSOCKET_TIMEOUT

    def get_stats(self):
        return None

    def connect(self) -> tuple[bool, str]:
        try:
            if self.is_connected:
                return True, ""
            self.client = Client(
                self.config.data["websocket_url"],
                headers={
                    "Cookie": RequestManager.format_cookie(
                        self.config.data["cookie"]
                    )
                },
                on_close_callback=self._on_close,
                sslopt=websocket_sslopt_for_config(self.config),
            )
            self._wrap_client_error_capture(self.client)
            self.client.connect(
                timeout=WEBSOCKET_TIMEOUT,
                connectCallback=lambda _: self.client.subscribe(  # receive event
                    destination=SUBSCRIPTION_DESTINATION,
                    callback=self._receive,
                ),
            )
            if self.disconnected:
                self.disconnect()
                return False, "Websocket disconnected"

            # logging.info("Websocket connected")
            self.is_connected = True
            self.is_auto_reconnecting = False
            if not self.first_conn_lost:
                self.first_conn_lost = True
                self.notification_manager.notify(
                    title=f"{APP_NAME}: WebSocket Connection Restored 🔗",
                    message="Connection re-established",
                )

            # send event
            self.clipboard_manager.on_copy(self.send)
            return True, "Websocket connected"
        except Exception as e:
            msg = f"Failed to connect websocket: {e}"
            logging.error(msg)
            return False, msg

    def _on_close(self):
        self.is_connected = False
        if self.is_login_phase or self.disconnected or self.is_reconnect_loop_running:
            return
        # Auto Reconnect
        self.is_reconnect_loop_running = True
        try:
            self.is_auto_reconnecting = True
            if self.first_conn_lost:
                self.notification_manager.notify(
                    title=f"{APP_NAME}: WebSocket Connection Lost ⛓️‍💥",
                    message="Check your internet connection. Retrying...",
                )
                self.first_conn_lost = False
            while not self.disconnected:
                time.sleep(RECONNECT_WS_TIMER)  # seconds
                if self.disconnected:
                    break
                last_error = (
                    getattr(self.client, "last_error", None) if self.client else None
                )
                if _is_rejected_session(last_error):
                    self._reauthenticate()
                connected, _ = self.connect()
                if connected:
                    break
        finally:
            self.is_reconnect_loop_running = False

    @staticmethod
    def _wrap_client_error_capture(client):
        """Record the websocket-client error onto the Client instance so
        _on_close can classify a lost connection, without patching
        stomp_ws/client.py: wraps the on_error handler Client's own
        constructor already installed on the underlying WebSocketApp."""
        client.last_error = None
        original_on_error = client.ws.on_error

        def _capture(ws_app, error, *args):
            client.last_error = error
            original_on_error(ws_app, error, *args)

        client.ws.on_error = _capture

    def _reauthenticate(self):
        """Refresh the cookie from the stored login digest when the server
        rejected the session (e.g. after a restart). A refused
        re-authentication still falls through to the reconnect attempt on
        the stale cookie; the reconnect loop then tries again every
        RECONNECT_WS_TIMER seconds."""
        login_successful, msg, cookie = self.request_manager.login()
        if login_successful:
            self.config.data["cookie"] = cookie
        else:
            logging.error(f"Re-authentication failed: {msg}")

    def send(self, payload: str, payload_type: str = "text"):
        try:
            if self.is_connected:
                if self.clipboard_manager.has_clipboard_changed(payload):
                    if self.config.data["cipher_enabled"]:
                        payload = CipherManager.encode_to_json_string(
                            **self.cipher_manager.encrypt(payload)
                        )
                    body = json.dumps({"payload": payload, "type": payload_type})
                    self.client.send(destination=SEND_DESTINATION, body=body)
        except Exception as e:
            logging.error(f"Failed to send data: {e}")

    def _receive(self, frame: any) -> str:
        try:
            if self.is_connected:
                body = json.loads(frame.body)
                payload = body["payload"]
                payload_type = body.get("type", "text")
                if self.config.data["cipher_enabled"]:
                    payload = self.cipher_manager.decrypt(
                        **CipherManager.decode_from_json_string(payload)
                    )

                if self.clipboard_manager.has_clipboard_changed(payload):
                    self.clipboard_manager.base64_to_clipboard(
                        base64_string=payload, type_=payload_type
                    )
        except json.decoder.JSONDecodeError:
            logging.error(
                "If cipher is enabled, please make sure it is enabled on all devices"
            )
        except Exception as e:
            logging.error(f"Failed to receive data: {e}")

    def manual_reconnect(self):
        if not self.is_auto_reconnecting:
            self.disconnected = False
            self.connect()

    def disconnect(self):
        try:
            self.clipboard_manager.previous_clipboard_hash = 0
            self.disconnected = True
            self.first_conn_lost = True
            try:
                self.client.disconnect()
                self.is_connected = False
                logging.info("Websocket disconnected")
            except Exception as e:
                pass  # silent catch
            self.clipboard_manager.stop()
        except Exception as e:
            logging.error(f"Failed to disconnect websocket: {e}")
