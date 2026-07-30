"""Task 9.4: confirms the headless-recovery patch (tasks 9.2-9.3) is scoped
to the P2S STOMP client path and does not reach P2PManager.

Run from ClipCascade_Desktop/src/:
    python3 -m unittest tests.test_p2s_scope_boundary -v
"""
import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from p2p.p2p_manager import P2PManager


class TestP2PManagerHasNoReauthentication(unittest.TestCase):
    """P2PManager.__init__ spawns a real asyncio event-loop thread, so these
    checks read the class's own source rather than instantiate it."""

    def test_no_reauthenticate_method(self):
        self.assertFalse(hasattr(P2PManager, "_reauthenticate"))

    def test_init_never_assigns_request_manager(self):
        source = inspect.getsource(P2PManager.__init__)
        self.assertNotIn("self.request_manager", source)

    def test_no_login_call_anywhere_in_class(self):
        source = inspect.getsource(P2PManager)
        self.assertNotIn(".login()", source)


if __name__ == "__main__":
    unittest.main()
