"""
Unit Tests for Push-to-Talk Voice Message Relay Handler (Bonus B4 / Special 4):
  - B4 Private: Unicast voice delivery to recipient + sender echo
  - B4 Private: Offline target returns ERR_USER_NOT_FOUND
  - B4 Group: Multicast voice clip strictly to joined group members
  - B4 Group: Non-member sending voice clip receives ERR_NOT_IN_GROUP
  - B4 Safeguards: Rejection of empty target/audio or oversized audio payloads
"""

import socket
import threading
import time
import unittest

from common.protocol import (
    ERR_GROUP_NOT_FOUND,
    ERR_INVALID_PACKET,
    ERR_NOT_IN_GROUP,
    ERR_USER_NOT_FOUND,
    KEY_PAYLOAD,
    KEY_TYPE,
    MSG_CLIENT_LIST,
    MSG_CREATE_GROUP,
    MSG_ERROR,
    MSG_GROUP_LIST,
    MSG_JOIN_GROUP,
    MSG_REGISTER,
    MSG_REGISTER_ACK,
    MSG_VOICE_MSG,
    ROOM_GROUP,
    ROOM_PRIVATE,
    SocketLineBuffer,
    encode_message,
)
from server.client_handler import handle_client
from server.handlers.audio import MAX_AUDIO_B64_BYTES
from server.state import ServerState

TEST_HOST = "127.0.0.1"
TEST_PORT = 5096

# Small valid base64-like dummy audio chunk
SAMPLE_AUDIO_B64 = "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="


class TestAudioHandler(unittest.TestCase):
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
                except (socket.timeout, OSError):
                    continue

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
        """Helper connecting client socket, consuming initial directory, and registering."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((TEST_HOST, TEST_PORT))
        buf = SocketLineBuffer(sock)

        # 1. Consume initial CLIENT_LIST broadcast on connect
        initial_list = buf.read_message()
        self.assertEqual(initial_list[KEY_TYPE], MSG_CLIENT_LIST)

        # 2. Send REGISTER
        sock.sendall(encode_message(MSG_REGISTER, {"username": username}))
        ack = buf.read_message()
        self.assertEqual(ack[KEY_TYPE], MSG_REGISTER_ACK)
        self.assertTrue(ack[KEY_PAYLOAD]["success"])

        # 3. Consume broadcast CLIENT_LIST and initial GROUP_LIST triggered by registration
        broadcast = buf.read_message()
        self.assertEqual(broadcast[KEY_TYPE], MSG_CLIENT_LIST)
        gl = buf.read_message()
        self.assertEqual(gl[KEY_TYPE], MSG_GROUP_LIST)

        return sock, buf

    def test_01_private_voice_delivery_and_echo(self):
        """B4: Alice sends voice to Bob -> Bob receives voice clip, Alice receives echo."""
        sock_alice, buf_alice = self._create_registered_client("VoiceAlice")
        sock_bob, buf_bob = self._create_registered_client("VoiceBob")

        # Alice consumes directory update from Bob's registration
        buf_alice.read_message()

        try:
            # Alice sends voice clip to Bob
            voice_pkt = {
                "room_type": ROOM_PRIVATE,
                "target": "VoiceBob",
                "audio_b64": SAMPLE_AUDIO_B64,
                "duration": 2.4,
            }
            sock_alice.sendall(encode_message(MSG_VOICE_MSG, voice_pkt))

            # Bob receives unicast voice packet
            bob_msg = buf_bob.read_message()
            self.assertEqual(bob_msg[KEY_TYPE], MSG_VOICE_MSG)
            self.assertEqual(bob_msg[KEY_PAYLOAD]["from"], "VoiceAlice")
            self.assertEqual(bob_msg[KEY_PAYLOAD]["target"], "VoiceBob")
            self.assertEqual(bob_msg[KEY_PAYLOAD]["room_type"], ROOM_PRIVATE)
            self.assertEqual(bob_msg[KEY_PAYLOAD]["audio_b64"], SAMPLE_AUDIO_B64)
            self.assertAlmostEqual(bob_msg[KEY_PAYLOAD]["duration"], 2.4)

            # Alice receives echo copy so local chatroom displays and plays it
            alice_msg = buf_alice.read_message()
            self.assertEqual(alice_msg[KEY_TYPE], MSG_VOICE_MSG)
            self.assertEqual(alice_msg[KEY_PAYLOAD]["from"], "VoiceAlice")
            self.assertEqual(alice_msg[KEY_PAYLOAD]["target"], "VoiceBob")
            self.assertEqual(alice_msg[KEY_PAYLOAD]["audio_b64"], SAMPLE_AUDIO_B64)
        finally:
            sock_alice.close()
            sock_bob.close()

    def test_02_private_voice_offline_recipient_error(self):
        """B4: Alice sends voice to an offline user -> receives ERR_USER_NOT_FOUND."""
        sock, buf = self._create_registered_client("SoloSender")
        try:
            sock.sendall(encode_message(MSG_VOICE_MSG, {
                "room_type": ROOM_PRIVATE,
                "target": "NonExistentUser",
                "audio_b64": SAMPLE_AUDIO_B64,
                "duration": 1.0,
            }))
            err = buf.read_message()
            self.assertEqual(err[KEY_TYPE], MSG_ERROR)
            self.assertEqual(err[KEY_PAYLOAD]["code"], ERR_USER_NOT_FOUND)
        finally:
            sock.close()

    def test_03_group_voice_multicast(self):
        """B4: Group member sends voice -> all joined members receive the clip."""
        sock_admin, buf_admin = self._create_registered_client("VoiceAdmin")
        sock_member, buf_member = self._create_registered_client("VoiceMember")

        # Admin consumes Member's connect broadcast
        buf_admin.read_message()

        try:
            # 1. Admin creates group 'RadioRoom'
            sock_admin.sendall(encode_message(MSG_CREATE_GROUP, {"group": "RadioRoom"}))
            # Admin and Member both consume GROUP_LIST broadcast
            buf_admin.read_message()
            buf_member.read_message()

            # 2. Member joins 'RadioRoom'
            sock_member.sendall(encode_message(MSG_JOIN_GROUP, {"group": "RadioRoom"}))
            # Both consume updated GROUP_LIST broadcast
            buf_admin.read_message()
            buf_member.read_message()

            # 3. Member sends voice message to 'RadioRoom'
            sock_member.sendall(encode_message(MSG_VOICE_MSG, {
                "room_type": ROOM_GROUP,
                "target": "RadioRoom",
                "audio_b64": SAMPLE_AUDIO_B64,
                "duration": 3.1,
            }))

            # Member receives their own message via group multicast
            member_rx = buf_member.read_message()
            self.assertEqual(member_rx[KEY_TYPE], MSG_VOICE_MSG)
            self.assertEqual(member_rx[KEY_PAYLOAD]["from"], "VoiceMember")
            self.assertEqual(member_rx[KEY_PAYLOAD]["target"], "RadioRoom")
            self.assertEqual(member_rx[KEY_PAYLOAD]["room_type"], ROOM_GROUP)
            self.assertEqual(member_rx[KEY_PAYLOAD]["audio_b64"], SAMPLE_AUDIO_B64)
            self.assertAlmostEqual(member_rx[KEY_PAYLOAD]["duration"], 3.1)

            # Admin also receives group multicast
            admin_rx = buf_admin.read_message()
            self.assertEqual(admin_rx[KEY_TYPE], MSG_VOICE_MSG)
            self.assertEqual(admin_rx[KEY_PAYLOAD]["from"], "VoiceMember")
            self.assertEqual(admin_rx[KEY_PAYLOAD]["target"], "RadioRoom")
            self.assertEqual(admin_rx[KEY_PAYLOAD]["audio_b64"], SAMPLE_AUDIO_B64)
        finally:
            sock_admin.close()
            sock_member.close()

    def test_04_group_voice_non_member_rejected(self):
        """B4: Outsider sending voice to group receives ERR_NOT_IN_GROUP."""
        sock_creator, buf_creator = self._create_registered_client("Podcaster")
        sock_outsider, buf_outsider = self._create_registered_client("Lurker")

        buf_creator.read_message()

        try:
            # Creator makes group
            sock_creator.sendall(encode_message(MSG_CREATE_GROUP, {"group": "VIPLounge"}))
            buf_creator.read_message()
            buf_outsider.read_message()

            # Outsider (not joined) attempts to send voice clip
            sock_outsider.sendall(encode_message(MSG_VOICE_MSG, {
                "room_type": ROOM_GROUP,
                "target": "VIPLounge",
                "audio_b64": SAMPLE_AUDIO_B64,
                "duration": 1.5,
            }))

            err = buf_outsider.read_message()
            self.assertEqual(err[KEY_TYPE], MSG_ERROR)
            self.assertEqual(err[KEY_PAYLOAD]["code"], ERR_NOT_IN_GROUP)
        finally:
            sock_creator.close()
            sock_outsider.close()

    def test_05_invalid_payload_rejected(self):
        """B4: Missing fields or oversized payload returns ERR_INVALID_PACKET."""
        sock, buf = self._create_registered_client("ValidatorClient")
        try:
            # Missing audio_b64
            sock.sendall(encode_message(MSG_VOICE_MSG, {
                "room_type": ROOM_PRIVATE,
                "target": "ValidatorClient",
                "audio_b64": "",
            }))
            err = buf.read_message()
            self.assertEqual(err[KEY_TYPE], MSG_ERROR)
            self.assertEqual(err[KEY_PAYLOAD]["code"], ERR_INVALID_PACKET)

            # Oversized payload exceeding 5MB
            fake_huge_audio = "A" * (MAX_AUDIO_B64_BYTES + 10)
            sock.sendall(encode_message(MSG_VOICE_MSG, {
                "room_type": ROOM_PRIVATE,
                "target": "ValidatorClient",
                "audio_b64": fake_huge_audio,
            }))
            err2 = buf.read_message()
            self.assertEqual(err2[KEY_TYPE], MSG_ERROR)
            self.assertEqual(err2[KEY_PAYLOAD]["code"], ERR_INVALID_PACKET)
        finally:
            sock.close()


if __name__ == "__main__":
    unittest.main()
