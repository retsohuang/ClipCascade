"""Unit tests for the websocket TLS options helper.

Run from ClipCascade_Desktop/src/:
    python3 -m unittest tests.test_ssl_helper -v
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.constants import MACOS
from utils import ssl_helper


def _config(websocket_url, ssl_ca_bundle=""):
    config = MagicMock()
    config.data = {"websocket_url": websocket_url, "ssl_ca_bundle": ssl_ca_bundle}
    return config


class TestWebsocketSslopt(unittest.TestCase):
    def setUp(self):
        platform_patch = patch.object(ssl_helper, "PLATFORM", MACOS)
        platform_patch.start()
        self.addCleanup(platform_patch.stop)
        certifi_patch = patch.object(ssl_helper, "certifi", create=True)
        self.certifi = certifi_patch.start()
        self.addCleanup(certifi_patch.stop)
        self.certifi.where.return_value = "/missing/certifi/cacert.pem"

    def test_ws_url_returns_none_without_reading_certifi(self):
        config = _config("ws://host:8080/clipsocket")

        self.assertIsNone(ssl_helper.websocket_sslopt_for_config(config))
        self.certifi.where.assert_not_called()

    def test_ws_url_ignores_a_missing_configured_ca_bundle(self):
        config = _config("ws://host:8080/clipsocket", "/missing/ca.pem")

        self.assertIsNone(ssl_helper.websocket_sslopt_for_config(config))

    def test_wss_url_on_macos_uses_certifi_bundle(self):
        config = _config("wss://host:8080/clipsocket")

        with patch.object(ssl_helper.ssl, "create_default_context") as create_context:
            sslopt = ssl_helper.websocket_sslopt_for_config(config)

        self.certifi.where.assert_called_once_with()
        create_context.assert_called_once_with(cafile="/missing/certifi/cacert.pem")
        self.assertEqual(sslopt, {"context": create_context.return_value})


if __name__ == "__main__":
    unittest.main()
