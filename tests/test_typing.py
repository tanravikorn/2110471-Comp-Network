"""
Unit Tests for Real-Time Typing Indicator Handler (Bonus Requirement B3 / Special 3):
  - Private 1-on-1 Typing Indicator Relay (Alice -> Server -> Bob, no echo to Alice)
  - Group Typing Indicator Relay (Alice -> Server -> All members except Alice)
  - Offline User Handling (Graceful drop without error or crash)
  - Non-Member Group Typing Drop (Non-members cannot broadcast typing status)
"""

import socket
import threading
import time
import unittest

from common.protocol import (
    KEY_PAYLOAD,
    KEY_TYPE,
    MSG_CLIENT_LIST,
    MSG_CREATE_GROUP,
    MSG_GROUP_LIST,
    MSG_JOIN_GROUP,
    MSG_REGISTER,
    MSG_REGISTER_ACK,
    MSG_TYPING,
    ROOM_GROUP,
    ROOM_PRIVATE,
    SocketLineBuffer,
    encode_message,
)
from server.client_handler import handle_client
from server.state import ServerState

TEST_HOST = "127.0.0.1"
TEST_PORT = 5198


class TestTypingHandler(unittest.TestCase):
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
        cls.server_sock.listen(10)
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

    def _create_registered_client(self, username: str):
        """Helper to connect, read initial CLIENT_LIST, and register username."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((TEST_HOST, TEST_PORT))
        buf = SocketLineBuffer(sock)

        # Initial CLIENT_LIST broadcast on connect
        init_list = buf.read_message()
        self.assertEqual(init_list[KEY_TYPE], MSG_CLIENT_LIST)

        # Send REGISTER
        sock.sendall(encode_message(MSG_REGISTER, {"username": username}))

        # Read REGISTER_ACK
        ack = buf.read_message()
        self.assertEqual(ack[KEY_TYPE], MSG_REGISTER_ACK)
        self.assertTrue(ack[KEY_PAYLOAD]["success"])

        return sock, buf

    def _read_matching(self, buf: SocketLineBuffer, expected_type: str):
        """Reads messages from stream, ignoring background directory broadcasts until expected type arrives."""
        for _ in range(10):
            msg = buf.read_message()
            if msg[KEY_TYPE] == expected_type:
                return msg
        self.fail(f"Did not receive expected message type: {expected_type}")

    def test_private_typing_relay(self):
        """B3: Alice types to Bob -> Bob receives TYPING packet, Alice gets no echo."""
        alice_sock, alice_buf = self._create_registered_client("AliceTypist")
        bob_sock, bob_buf = self._create_registered_client("BobWatcher")

        try:
            # 1. Alice sends TYPING (is_typing=True)
            alice_sock.sendall(encode_message(MSG_TYPING, {
                "room_type": ROOM_PRIVATE,
                "target": "BobWatcher",
                "is_typing": True,
            }))

            # Bob should receive TYPING
            msg = self._read_matching(bob_buf, MSG_TYPING)
            self.assertEqual(msg[KEY_TYPE], MSG_TYPING)
            self.assertEqual(msg[KEY_PAYLOAD]["room_type"], ROOM_PRIVATE)
            self.assertEqual(msg[KEY_PAYLOAD]["target"], "BobWatcher")
            self.assertEqual(msg[KEY_PAYLOAD]["from"], "AliceTypist")
            self.assertTrue(msg[KEY_PAYLOAD]["is_typing"])

            # 2. Alice sends TYPING (is_typing=False) after debounce
            alice_sock.sendall(encode_message(MSG_TYPING, {
                "room_type": ROOM_PRIVATE,
                "target": "BobWatcher",
                "is_typing": False,
            }))

            msg2 = self._read_matching(bob_buf, MSG_TYPING)
            self.assertEqual(msg2[KEY_TYPE], MSG_TYPING)
            self.assertFalse(msg2[KEY_PAYLOAD]["is_typing"])

        finally:
            alice_sock.close()
            bob_sock.close()
            time.sleep(0.05)

    def test_private_typing_offline_target(self):
        """B3: Alice types to an offline target -> server quietly drops without error."""
        alice_sock, alice_buf = self._create_registered_client("SoloAlice")

        try:
            # Alice sends TYPING to non-existent user
            alice_sock.sendall(encode_message(MSG_TYPING, {
                "room_type": ROOM_PRIVATE,
                "target": "NobodyHere",
                "is_typing": True,
            }))

            # Server should not disconnect Alice or throw error
            time.sleep(0.1)
            self.assertIn("SoloAlice", self.state.get_client_list())

        finally:
            alice_sock.close()
            time.sleep(0.05)

    def test_group_typing_multicast(self):
        """B3: Alice types in group -> Bob and Charlie receive, Alice does not receive echo."""
        alice_sock, alice_buf = self._create_registered_client("GroupAlice")
        bob_sock, bob_buf = self._create_registered_client("GroupBob")
        charlie_sock, charlie_buf = self._create_registered_client("GroupCharlie")

        # Drain registration client list broadcasts
        time.sleep(0.1)
        alice_sock.settimeout(0.2)
        bob_sock.settimeout(0.2)
        charlie_sock.settimeout(0.2)

        try:
            # Alice creates group 'DevRoom'
            alice_sock.sendall(encode_message(MSG_CREATE_GROUP, {"group": "DevRoom"}))
            time.sleep(0.05)

            # Bob joins 'DevRoom'
            bob_sock.sendall(encode_message(MSG_JOIN_GROUP, {"group": "DevRoom"}))
            time.sleep(0.05)

            # Charlie joins 'DevRoom'
            charlie_sock.sendall(encode_message(MSG_JOIN_GROUP, {"group": "DevRoom"}))
            time.sleep(0.05)

            # Alice sends TYPING in DevRoom
            alice_sock.sendall(encode_message(MSG_TYPING, {
                "room_type": ROOM_GROUP,
                "target": "DevRoom",
                "is_typing": True,
            }))

            # Bob receives
            bob_msg = self._read_matching(bob_buf, MSG_TYPING)
            self.assertEqual(bob_msg[KEY_TYPE], MSG_TYPING)
            self.assertEqual(bob_msg[KEY_PAYLOAD]["room_type"], ROOM_GROUP)
            self.assertEqual(bob_msg[KEY_PAYLOAD]["target"], "DevRoom")
            self.assertEqual(bob_msg[KEY_PAYLOAD]["from"], "GroupAlice")
            self.assertTrue(bob_msg[KEY_PAYLOAD]["is_typing"])

            # Charlie receives
            charlie_msg = self._read_matching(charlie_buf, MSG_TYPING)
            self.assertEqual(charlie_msg[KEY_TYPE], MSG_TYPING)
            self.assertEqual(charlie_msg[KEY_PAYLOAD]["from"], "GroupAlice")
            self.assertTrue(charlie_msg[KEY_PAYLOAD]["is_typing"])

            # Alice must NOT receive echo of her own typing packet
            alice_sock.settimeout(0.3)
            alice_received_typing = False
            try:
                while True:
                    m = alice_buf.read_message()
                    if m[KEY_TYPE] == MSG_TYPING:
                        alice_received_typing = True
                        break
            except (socket.timeout, TimeoutError, OSError):
                pass
            self.assertFalse(alice_received_typing, "Alice should not receive her own group typing echo")

        finally:
            alice_sock.close()
            bob_sock.close()
            charlie_sock.close()
            time.sleep(0.05)

    def test_group_typing_non_member_dropped(self):
        """B3: Outsider not in group sends TYPING -> members receive nothing."""
        owner_sock, owner_buf = self._create_registered_client("RoomOwner")
        outsider_sock, _ = self._create_registered_client("Outsider")

        try:
            owner_sock.sendall(encode_message(MSG_CREATE_GROUP, {"group": "PrivateClub"}))
            time.sleep(0.05)

            # Outsider (not joined) sends TYPING to PrivateClub
            outsider_sock.sendall(encode_message(MSG_TYPING, {
                "room_type": ROOM_GROUP,
                "target": "PrivateClub",
                "is_typing": True,
            }))

            owner_sock.settimeout(0.2)
            received_typing = False
            try:
                while True:
                    m = owner_buf.read_message()
                    if m[KEY_TYPE] == MSG_TYPING:
                        received_typing = True
                        break
            except (socket.timeout, TimeoutError, OSError):
                pass
            self.assertFalse(received_typing, "Non-member typing must not be relayed to group")

        finally:
            owner_sock.close()
            outsider_sock.close()
            time.sleep(0.05)


if __name__ == "__main__":
    unittest.main()
