"""
Test for Modular Register Handler (Requirement R3 & R4):
  - R3: Each client must have a unique name.
  - R4: Each client can see a list of names of all clients that are currently connected (including itself).
"""

import json
import socket
import threading
import time
import unittest

from common.protocol import (
    ERR_NOT_REGISTERED,
    KEY_PAYLOAD,
    KEY_TYPE,
    MSG_CLIENT_LIST,
    MSG_ERROR,
    MSG_REGISTER,
    MSG_REGISTER_ACK,
    SocketLineBuffer,
    encode_message,
)
from server.client_handler import handle_client
from server.state import ServerState

TEST_HOST = "127.0.0.1"
TEST_PORT = 5077


class TestRegisterHandler(unittest.TestCase):
    server_sock: socket.socket
    server_thread: threading.Thread
    state: ServerState
    running: bool

    @classmethod
    def setUpClass(cls):
        cls.state = ServerState()
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
                        args=(client_sock, client_addr, cls.state),
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
        cls.running = False
        try:
            cls.server_sock.close()
        except OSError:
            pass
        cls.server_thread.join(timeout=1.0)

    def _connect(self) -> tuple[socket.socket, SocketLineBuffer]:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect((TEST_HOST, TEST_PORT))
        buf = SocketLineBuffer(client)
        return client, buf

    def test_01_empty_username_rejected(self):
        """Empty or whitespace-only username must be rejected (R3)."""
        sock, buf = self._connect()
        try:
            sock.sendall(encode_message(MSG_REGISTER, {"username": "   "}))
            ack = buf.read_message()
            self.assertEqual(ack[KEY_TYPE], MSG_REGISTER_ACK)
            self.assertFalse(ack[KEY_PAYLOAD]["success"])
            self.assertIn("cannot be empty", ack[KEY_PAYLOAD]["message"])
        finally:
            sock.close()

    def test_02_register_unique_and_duplicate(self):
        """First client gets registered; second client with same name is rejected (R3, R4)."""
        alice_sock, alice_buf = self._connect()
        bob_sock, bob_buf = self._connect()

        try:
            # 1. Alice registers -> Success
            alice_sock.sendall(encode_message(MSG_REGISTER, {"username": "Alice"}))
            ack = alice_buf.read_message()
            self.assertEqual(ack[KEY_TYPE], MSG_REGISTER_ACK)
            self.assertTrue(ack[KEY_PAYLOAD]["success"])

            # Alice receives CLIENT_LIST with her own name (R4)
            cl1 = alice_buf.read_message()
            self.assertEqual(cl1[KEY_TYPE], MSG_CLIENT_LIST)
            self.assertIn("Alice", cl1[KEY_PAYLOAD]["clients"])

            # 2. Bob tries to register as "Alice" -> Rejected!
            bob_sock.sendall(encode_message(MSG_REGISTER, {"username": "Alice"}))
            dup_ack = bob_buf.read_message()
            self.assertEqual(dup_ack[KEY_TYPE], MSG_REGISTER_ACK)
            self.assertFalse(dup_ack[KEY_PAYLOAD]["success"])
            self.assertIn("already taken", dup_ack[KEY_PAYLOAD]["message"])

            # 3. Bob registers as "Bob" -> Success
            bob_sock.sendall(encode_message(MSG_REGISTER, {"username": "Bob"}))
            bob_ack = bob_buf.read_message()
            self.assertEqual(bob_ack[KEY_TYPE], MSG_REGISTER_ACK)
            self.assertTrue(bob_ack[KEY_PAYLOAD]["success"])

            # Alice receives broadcast updated CLIENT_LIST with [Alice, Bob] (R4)
            alice_cl2 = alice_buf.read_message()
            self.assertEqual(alice_cl2[KEY_TYPE], MSG_CLIENT_LIST)
            self.assertEqual(sorted(alice_cl2[KEY_PAYLOAD]["clients"]), ["Alice", "Bob"])

            # Bob also receives CLIENT_LIST with [Alice, Bob] (R4)
            bob_cl = bob_buf.read_message()
            self.assertEqual(bob_cl[KEY_TYPE], MSG_CLIENT_LIST)
            self.assertEqual(sorted(bob_cl[KEY_PAYLOAD]["clients"]), ["Alice", "Bob"])

        finally:
            alice_sock.close()
            bob_sock.close()

    def test_03_disconnect_cleanup(self):
        """When a registered client disconnects, remaining clients receive updated list."""
        c1_sock, c1_buf = self._connect()
        c2_sock, c2_buf = self._connect()

        try:
            c1_sock.sendall(encode_message(MSG_REGISTER, {"username": "TempUser1"}))
            c1_buf.read_message()  # ACK
            c1_buf.read_message()  # CLIENT_LIST

            c2_sock.sendall(encode_message(MSG_REGISTER, {"username": "TempUser2"}))
            c2_buf.read_message()  # ACK
            c2_buf.read_message()  # CLIENT_LIST
            c1_buf.read_message()  # Update for c1

            # Disconnect TempUser1
            c1_sock.close()

            # TempUser2 must receive updated CLIENT_LIST without TempUser1
            c2_update = c2_buf.read_message()
            self.assertEqual(c2_update[KEY_TYPE], MSG_CLIENT_LIST)
            self.assertNotIn("TempUser1", c2_update[KEY_PAYLOAD]["clients"])
            self.assertIn("TempUser2", c2_update[KEY_PAYLOAD]["clients"])

        finally:
            c2_sock.close()


if __name__ == "__main__":
    unittest.main()
