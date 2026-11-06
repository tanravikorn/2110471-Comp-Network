"""
Test for Requirement R2:
"The chat messages between the server and each client must be implemented using Socket Programming only"
Verifies:
  - Raw TCP socket connection (`socket.socket`, `connect`, `accept`)
  - Newline-delimited JSON stream transmission over socket
  - Server receives JSON message from client socket
  - Server sends JSON response back to client socket
"""

import json
import socket
import threading
import time
import unittest

from common.protocol import (
    KEY_PAYLOAD,
    KEY_TYPE,
    SocketLineBuffer,
    encode_message,
)
from server.client_handler import handle_client

TEST_HOST = "127.0.0.1"
TEST_PORT = 5088


class TestSocketR2(unittest.TestCase):
    server_sock: socket.socket
    server_thread: threading.Thread
    running: bool

    @classmethod
    def setUpClass(cls):
        """Starts a minimal TCP Server socket on TEST_PORT."""
        cls.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cls.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        cls.server_sock.bind((TEST_HOST, TEST_PORT))
        cls.server_sock.listen(5)
        cls.running = True

        def accept_loop():
            while cls.running:
                try:
                    cls.server_sock.settimeout(0.5)
                    client_sock, client_addr = cls.server_sock.accept()
                    t = threading.Thread(
                        target=handle_client,
                        args=(client_sock, client_addr),
                        daemon=True,
                    )
                    t.start()
                except socket.timeout:
                    continue
                except OSError:
                    break

        cls.server_thread = threading.Thread(target=accept_loop, daemon=True)
        cls.server_thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        """Closes server socket."""
        cls.running = False
        try:
            cls.server_sock.close()
        except OSError:
            pass
        cls.server_thread.join(timeout=1.0)

    def test_r2_socket_json_exchange(self):
        """Verifies sending and receiving JSON messages over raw TCP socket (R2)."""
        # 1. Create client socket using Python's standard socket library (R2)
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.connect((TEST_HOST, TEST_PORT))
        buf = SocketLineBuffer(client_sock)

        try:
            # 2. Client sends a JSON message over the TCP socket
            msg_sent = {
                "type": "REGISTER",
                "payload": {"username": "R2Tester"},
            }
            client_sock.sendall(encode_message(msg_sent))

            # 3. Client receives JSON response from server over the TCP socket
            response = buf.read_message()

            self.assertEqual(response[KEY_TYPE], "REGISTER_ACK")
            self.assertTrue(response[KEY_PAYLOAD]["success"])

        finally:
            client_sock.close()


if __name__ == "__main__":
    unittest.main()
