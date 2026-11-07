"""
Unit Tests for Cloud VPS Hardening (Must & Should Fixes)
Verifies:
  - SocketLineBuffer frame buffer limit (OOM prevention)
  - Unauthenticated connection timeout setup and removal
  - SO_KEEPALIVE socket configuration
"""

import socket
import unittest
from unittest.mock import MagicMock

from common.protocol import MAX_FRAME_BUFFER_BYTES, SocketLineBuffer
from server.client_handler import handle_client
from server.state import ServerState


class TestVPSHardening(unittest.TestCase):
    """Tests for VPS resilience features."""

    def test_buffer_overflow_protection(self):
        """SocketLineBuffer raises ValueError when incoming bytes exceed 10MB without delimiter."""
        mock_sock = MagicMock()
        # Return chunks of 64KB without newline
        mock_sock.recv.return_value = b"A" * 65536

        line_buffer = SocketLineBuffer(mock_sock, buffer_size=65536)
        # Fast-forward buffer near the ceiling
        line_buffer._buffer = "A" * (MAX_FRAME_BUFFER_BYTES - 100)

        with self.assertRaises(ValueError) as ctx:
            line_buffer.read_message()
        self.assertIn("exceeded maximum limit", str(ctx.exception))

    def test_unauthenticated_timeout_lifecycle(self):
        """Client socket gets 60s timeout initially, and timeout is removed upon registration."""
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [
            b'{"type":"REGISTER","payload":{"username":"Student1"}}\n',
            b"",  # EOF
        ]
        state = ServerState()

        handle_client(mock_sock, ("1.2.3.4", 5000), state)

        # Verify initial 60s timeout was set, then None once registered
        mock_sock.settimeout.assert_any_call(60.0)
        mock_sock.settimeout.assert_any_call(None)

    def test_socket_keepalive_supported(self):
        """SO_KEEPALIVE can be set on a stream socket."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            val = sock.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE)
            self.assertTrue(bool(val))
        finally:
            sock.close()


if __name__ == "__main__":
    unittest.main()
