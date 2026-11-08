"""
Unit Tests for Private and Group Messaging Handlers (Requirements R7, R8, R9, R10, R11):
  - R7: Private 1-on-1 Messaging (Unicast delivery + Sender echo + Offline target error)
  - R8: Create Group (Creator is initial member)
  - R9: Group List Directory Broadcast (All clients see groups and member lists)
  - R10: Self-Join Group (Explicit user join)
  - R11: Group Messaging (Multicast strictly to joined group members; non-members rejected)
"""

import socket
import threading
import time
import unittest

from common.protocol import (
    ERR_GROUP_EXISTS,
    ERR_NOT_IN_GROUP,
    ERR_USER_NOT_FOUND,
    KEY_PAYLOAD,
    KEY_TYPE,
    MSG_CLIENT_LIST,
    MSG_CREATE_GROUP,
    MSG_ERROR,
    MSG_GROUP,
    MSG_GROUP_LIST,
    MSG_JOIN_GROUP,
    MSG_PRIVATE,
    MSG_REGISTER,
    MSG_REGISTER_ACK,
    SocketLineBuffer,
    encode_message,
)
from server.client_handler import handle_client
from server.state import ServerState

TEST_HOST = "127.0.0.1"
TEST_PORT = 5099


class TestMessagingHandlers(unittest.TestCase):
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

    def _connect_and_register(self, username: str) -> tuple[socket.socket, SocketLineBuffer]:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect((TEST_HOST, TEST_PORT))
        buf = SocketLineBuffer(client)

        # 1. Read initial CLIENT_LIST sent upon connection
        buf.read_message()

        # 2. Register
        client.sendall(encode_message(MSG_REGISTER, {"username": username}))
        ack = buf.read_message()
        self.assertEqual(ack[KEY_TYPE], MSG_REGISTER_ACK)
        self.assertTrue(ack[KEY_PAYLOAD]["success"])

        # 3. Read broadcast CLIENT_LIST and initial GROUP_LIST resulting from registration
        buf.read_message()
        buf.read_message()
        return client, buf

    def test_01_private_msg_delivery_and_echo(self):
        """R7: Alice sends to Bob -> Bob receives unicast, Alice receives echo."""
        alice_sock, alice_buf = self._connect_and_register("Alice")

        # Bob connects -> Alice receives Bob's CLIENT_LIST broadcast
        bob_sock, bob_buf = self._connect_and_register("Bob")
        alice_buf.read_message()  # Bob's join broadcast

        try:
            # Alice sends private message to Bob
            alice_sock.sendall(encode_message(MSG_PRIVATE, {
                "to": "Bob",
                "text": "Hello Bob!"
            }))

            # Bob receives unicast
            bob_msg = bob_buf.read_message()
            self.assertEqual(bob_msg[KEY_TYPE], MSG_PRIVATE)
            self.assertEqual(bob_msg[KEY_PAYLOAD]["from"], "Alice")
            self.assertEqual(bob_msg[KEY_PAYLOAD]["to"], "Bob")
            self.assertEqual(bob_msg[KEY_PAYLOAD]["text"], "Hello Bob!")

            # Alice receives echo
            alice_echo = alice_buf.read_message()
            self.assertEqual(alice_echo[KEY_TYPE], MSG_PRIVATE)
            self.assertEqual(alice_echo[KEY_PAYLOAD]["from"], "Alice")
            self.assertEqual(alice_echo[KEY_PAYLOAD]["to"], "Bob")
            self.assertEqual(alice_echo[KEY_PAYLOAD]["text"], "Hello Bob!")
        finally:
            alice_sock.close()
            bob_sock.close()
            time.sleep(0.05)

    def test_02_private_msg_offline_user_error(self):
        """R7: Alice sends to offline user -> receives ERR_USER_NOT_FOUND."""
        alice_sock, alice_buf = self._connect_and_register("Alice2")
        try:
            alice_sock.sendall(encode_message(MSG_PRIVATE, {
                "to": "GhostUser",
                "text": "Are you there?"
            }))
            err_msg = alice_buf.read_message()
            self.assertEqual(err_msg[KEY_TYPE], MSG_ERROR)
            self.assertEqual(err_msg[KEY_PAYLOAD]["code"], ERR_USER_NOT_FOUND)
        finally:
            alice_sock.close()
            time.sleep(0.05)

    def test_03_group_lifecycle_and_messaging(self):
        """R8, R9, R10, R11: Create group, join group, multicast to members only."""
        u1_sock, u1_buf = self._connect_and_register("User1")
        u2_sock, u2_buf = self._connect_and_register("User2")
        u1_buf.read_message()  # U2 connect broadcast

        u3_sock, u3_buf = self._connect_and_register("User3")
        u1_buf.read_message()  # U3 connect broadcast
        u2_buf.read_message()  # U3 connect broadcast

        try:
            # 1. User1 creates group "PythonRoom" (R8)
            u1_sock.sendall(encode_message(MSG_CREATE_GROUP, {"group": "PythonRoom"}))

            # R9: All clients receive GROUP_LIST broadcast
            u1_gl = u1_buf.read_message()
            self.assertEqual(u1_gl[KEY_TYPE], MSG_GROUP_LIST)
            self.assertIn("PythonRoom", u1_gl[KEY_PAYLOAD]["groups"])
            self.assertEqual(u1_gl[KEY_PAYLOAD]["groups"]["PythonRoom"], ["User1"])

            u2_gl = u2_buf.read_message()
            self.assertEqual(u2_gl[KEY_TYPE], MSG_GROUP_LIST)

            u3_gl = u3_buf.read_message()
            self.assertEqual(u3_gl[KEY_TYPE], MSG_GROUP_LIST)

            # 2. Duplicate group name rejected (R8)
            u2_sock.sendall(encode_message(MSG_CREATE_GROUP, {"group": "PythonRoom"}))
            dup_err = u2_buf.read_message()
            self.assertEqual(dup_err[KEY_TYPE], MSG_ERROR)
            self.assertEqual(dup_err[KEY_PAYLOAD]["code"], ERR_GROUP_EXISTS)

            # 3. User2 joins "PythonRoom" (R10)
            u2_sock.sendall(encode_message(MSG_JOIN_GROUP, {"group": "PythonRoom"}))

            # R9: Both receive updated GROUP_LIST showing User1 and User2
            u1_gl2 = u1_buf.read_message()
            self.assertEqual(sorted(u1_gl2[KEY_PAYLOAD]["groups"]["PythonRoom"]), ["User1", "User2"])
            u2_gl2 = u2_buf.read_message()
            self.assertEqual(sorted(u2_gl2[KEY_PAYLOAD]["groups"]["PythonRoom"]), ["User1", "User2"])
            u3_gl2 = u3_buf.read_message()
            self.assertEqual(sorted(u3_gl2[KEY_PAYLOAD]["groups"]["PythonRoom"]), ["User1", "User2"])

            # 4. User3 (non-member) tries to send message to "PythonRoom" -> Rejected! (R11)
            u3_sock.sendall(encode_message(MSG_GROUP, {
                "group": "PythonRoom",
                "text": "I am not in this group!"
            }))
            not_in_err = u3_buf.read_message()
            self.assertEqual(not_in_err[KEY_TYPE], MSG_ERROR)
            self.assertEqual(not_in_err[KEY_PAYLOAD]["code"], ERR_NOT_IN_GROUP)

            # 5. User1 sends message to "PythonRoom" -> Only User1 and User2 receive it! (R11)
            u1_sock.sendall(encode_message(MSG_GROUP, {
                "group": "PythonRoom",
                "text": "Welcome to PythonRoom!"
            }))

            u1_grp_msg = u1_buf.read_message()
            self.assertEqual(u1_grp_msg[KEY_TYPE], MSG_GROUP)
            self.assertEqual(u1_grp_msg[KEY_PAYLOAD]["group"], "PythonRoom")
            self.assertEqual(u1_grp_msg[KEY_PAYLOAD]["from"], "User1")
            self.assertEqual(u1_grp_msg[KEY_PAYLOAD]["text"], "Welcome to PythonRoom!")

            u2_grp_msg = u2_buf.read_message()
            self.assertEqual(u2_grp_msg[KEY_TYPE], MSG_GROUP)
            self.assertEqual(u2_grp_msg[KEY_PAYLOAD]["from"], "User1")
            self.assertEqual(u2_grp_msg[KEY_PAYLOAD]["text"], "Welcome to PythonRoom!")

            # 6. Disconnect User2 -> User1 receives updated CLIENT_LIST and GROUP_LIST (R9)
            u2_sock.close()
            cl_update = u1_buf.read_message()
            self.assertEqual(cl_update[KEY_TYPE], MSG_CLIENT_LIST)
            self.assertNotIn("User2", cl_update[KEY_PAYLOAD]["clients"])

            gl_update = u1_buf.read_message()
            self.assertEqual(gl_update[KEY_TYPE], MSG_GROUP_LIST)
            self.assertEqual(gl_update[KEY_PAYLOAD]["groups"]["PythonRoom"], ["User1"])
            u3_buf.read_message()  # U2 disconnect CLIENT_LIST
            u3_buf.read_message()  # U2 disconnect GROUP_LIST

            # 7. Disconnect User1 (last member) -> PythonRoom is auto-deleted
            u1_sock.close()
            u3_buf.read_message()  # U1 disconnect CLIENT_LIST
            gl_empty = u3_buf.read_message()
            self.assertEqual(gl_empty[KEY_TYPE], MSG_GROUP_LIST)
            self.assertNotIn("PythonRoom", gl_empty[KEY_PAYLOAD]["groups"])

        finally:
            u1_sock.close()
            u3_sock.close()
            time.sleep(0.05)


if __name__ == "__main__":
    unittest.main()
