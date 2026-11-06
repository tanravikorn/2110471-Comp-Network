"""
Module: tests/test_client_requirements.py
Purpose: Requirement-by-Requirement Test Suite (R2 to R11 & Bonuses)
Run command: python -m unittest -v tests.test_client_requirements
"""

import json
import queue
import socket
import threading
import unittest

from client.network import NetworkClient
from common.protocol import (
    DELIMITER,
    ENCODING,
    MSG_AI_SUMMARY_REQ,
    MSG_AI_SUMMARY_RES,
    MSG_CLIENT_LIST,
    MSG_CREATE_GROUP,
    MSG_GROUP,
    MSG_GROUP_LIST,
    MSG_JOIN_GROUP,
    MSG_PRIVATE,
    MSG_REGISTER,
    MSG_REGISTER_ACK,
    MSG_TYPING,
    MSG_VOICE_MSG,
)


class TestClientRequirements(unittest.TestCase):

    def setUp(self):
        """Creates socket pair and client network instance before each test."""
        self.client_sock, self.server_sock = socket.socketpair()
        self.incoming_queue = queue.Queue()
        self.client = NetworkClient(self.incoming_queue)
        self.client.sock = self.client_sock
        self.client.connected = True

    def tearDown(self):
        """Cleans up sockets and background threads after each test."""
        if self.client.connected:
            self.client.disconnect()
        try:
            self.client_sock.close()
        except OSError:
            pass
        try:
            self.server_sock.close()
        except OSError:
            pass

    def _start_receive_thread(self) -> threading.Thread:
        """Helper to start the client receive thread in background."""
        rx_thread = threading.Thread(target=self.client._receive_loop, daemon=True)
        rx_thread.start()
        return rx_thread

    def _read_server_wire(self) -> dict:
        """Helper to read and parse a single raw packet delivered to the server socket."""
        raw_bytes = self.server_sock.recv(16384)
        raw_text = raw_bytes.decode(ENCODING)
        return json.loads(raw_text.strip())

    def _write_server_wire(self, msg_type: str, payload: dict) -> None:
        """Helper to send a JSON message envelope from server socket to client socket."""
        envelope = {
            "type": msg_type,
            "timestamp": "12:00:00",
            "payload": payload,
        }
        wire_data = (json.dumps(envelope) + DELIMITER).encode(ENCODING)
        self.server_sock.sendall(wire_data)

    # =========================================================================
    # R2: Socket Programming Only (TCP Socket & Demuxing)
    # =========================================================================

    def test_R2_socket_transmission_and_disconnection(self):
        """R2: Verifies TCP socket packet transmission and clean disconnection."""
        self.client.send_packet("R2_PING", {"data": "test"})
        received = self._read_server_wire()
        self.assertEqual(received["type"], "R2_PING")

        self.client.disconnect()
        self.assertFalse(self.client.connected)
        self.assertIsNone(self.client.sock)

    def test_R2_socket_stream_line_buffering(self):
        """R2: Verifies newline-delimited stream demuxing across TCP socket."""
        rx_thread = self._start_receive_thread()

        self._write_server_wire("R2_STREAM_1", {"seq": 1})
        self._write_server_wire("R2_STREAM_2", {"seq": 2})

        msg1 = self.incoming_queue.get(timeout=2.0)
        msg2 = self.incoming_queue.get(timeout=2.0)

        self.assertEqual(msg1["type"], "R2_STREAM_1")
        self.assertEqual(msg2["type"], "R2_STREAM_2")

    # =========================================================================
    # R3: Unique Client Registration
    # =========================================================================

    def test_R3_client_registration_flow(self):
        """R3: Verifies client sending REGISTER packet and receiving REGISTER_ACK response."""
        rx_thread = self._start_receive_thread()

        self.client.send_packet(MSG_REGISTER, {"username": "Alice"})
        sent_packet = self._read_server_wire()
        self.assertEqual(sent_packet["type"], MSG_REGISTER)
        self.assertEqual(sent_packet["payload"]["username"], "Alice")

        self._write_server_wire(MSG_REGISTER_ACK, {"status": "SUCCESS", "username": "Alice"})
        ack = self.incoming_queue.get(timeout=2.0)
        self.assertEqual(ack["type"], MSG_REGISTER_ACK)
        self.assertEqual(ack["payload"]["status"], "SUCCESS")

    # =========================================================================
    # R4: Connected Client List Directory
    # =========================================================================

    def test_R4_receive_online_client_list(self):
        """R4: Verifies client receiving broadcasted CLIENT_LIST active directory updates."""
        rx_thread = self._start_receive_thread()

        self._write_server_wire(MSG_CLIENT_LIST, {"users": ["Alice", "Bob", "Charlie"]})
        msg = self.incoming_queue.get(timeout=2.0)
        self.assertEqual(msg["type"], MSG_CLIENT_LIST)
        self.assertListEqual(msg["payload"]["users"], ["Alice", "Bob", "Charlie"])

    # =========================================================================
    # R5 & R6: Message Protocol Framing & Envelope Structure
    # =========================================================================

    def test_R5_R6_envelope_structure_validation(self):
        """R5/R6: Verifies all outbound messages contain 'type', 'timestamp', and 'payload'."""
        self.client.send_packet("TEST_FORMAT", {"content": "Hello"})
        packet = self._read_server_wire()

        self.assertIn("type", packet)
        self.assertIn("timestamp", packet)
        self.assertIn("payload", packet)
        self.assertEqual(packet["type"], "TEST_FORMAT")
        self.assertEqual(packet["payload"]["content"], "Hello")

    # =========================================================================
    # R7: Private 1-on-1 Messaging
    # =========================================================================

    def test_R7_private_message_transmission(self):
        """R7: Verifies sending and receiving 1-on-1 private chat messages."""
        rx_thread = self._start_receive_thread()

        self.client.send_packet(MSG_PRIVATE, {"to": "Bob", "text": "Secret hello"})
        sent = self._read_server_wire()
        self.assertEqual(sent["type"], MSG_PRIVATE)
        self.assertEqual(sent["payload"]["to"], "Bob")
        self.assertEqual(sent["payload"]["text"], "Secret hello")

        self._write_server_wire(MSG_PRIVATE, {"from": "Bob", "text": "Reply hello"})
        recv = self.incoming_queue.get(timeout=2.0)
        self.assertEqual(recv["type"], MSG_PRIVATE)
        self.assertEqual(recv["payload"]["from"], "Bob")

    # =========================================================================
    # R8: Group Creation
    # =========================================================================

    def test_R8_create_group_request(self):
        """R8: Verifies client transmitting CREATE_GROUP request to server."""
        self.client.send_packet(MSG_CREATE_GROUP, {"group": "StudyGroup"})
        sent = self._read_server_wire()
        self.assertEqual(sent["type"], MSG_CREATE_GROUP)
        self.assertEqual(sent["payload"]["group"], "StudyGroup")

    # =========================================================================
    # R9: Group Directory List & Member Discovery
    # =========================================================================

    def test_R9_receive_group_list_directory(self):
        """R9: Verifies client receiving GROUP_LIST with group names and member lists."""
        rx_thread = self._start_receive_thread()

        group_data = {"StudyGroup": ["Alice", "Bob"], "Gaming": ["Charlie"]}
        self._write_server_wire(MSG_GROUP_LIST, {"groups": group_data})

        msg = self.incoming_queue.get(timeout=2.0)
        self.assertEqual(msg["type"], MSG_GROUP_LIST)
        self.assertDictEqual(msg["payload"]["groups"], group_data)

    # =========================================================================
    # R10: Self-Join Group
    # =========================================================================

    def test_R10_join_group_request(self):
        """R10: Verifies client transmitting JOIN_GROUP request."""
        self.client.send_packet(MSG_JOIN_GROUP, {"group": "StudyGroup"})
        sent = self._read_server_wire()
        self.assertEqual(sent["type"], MSG_JOIN_GROUP)
        self.assertEqual(sent["payload"]["group"], "StudyGroup")

    # =========================================================================
    # R11: Group Messaging
    # =========================================================================

    def test_R11_group_message_transmission(self):
        """R11: Verifies sending and receiving multi-client group room messages."""
        rx_thread = self._start_receive_thread()

        self.client.send_packet(MSG_GROUP, {"group": "StudyGroup", "text": "Hello group!"})
        sent = self._read_server_wire()
        self.assertEqual(sent["type"], MSG_GROUP)
        self.assertEqual(sent["payload"]["group"], "StudyGroup")

        self._write_server_wire(MSG_GROUP, {"group": "StudyGroup", "from": "Bob", "text": "Hey Alice!"})
        recv = self.incoming_queue.get(timeout=2.0)
        self.assertEqual(recv["type"], MSG_GROUP)
        self.assertEqual(recv["payload"]["from"], "Bob")

    # =========================================================================
    # Bonus B1: AI Chat Summarization
    # =========================================================================

    def test_B1_ai_summary_request_and_response(self):
        """B1: Verifies client requesting AI history summary and receiving summary response."""
        rx_thread = self._start_receive_thread()

        self.client.send_packet(MSG_AI_SUMMARY_REQ, {"room_type": "GROUP", "target": "StudyGroup"})
        sent = self._read_server_wire()
        self.assertEqual(sent["type"], MSG_AI_SUMMARY_REQ)

        summary_text = "• Discussed network protocols\n• Assigned R2 socket task"
        self._write_server_wire(MSG_AI_SUMMARY_RES, {
            "room_type": "GROUP",
            "target": "StudyGroup",
            "summary": summary_text
        })

        recv = self.incoming_queue.get(timeout=2.0)
        self.assertEqual(recv["type"], MSG_AI_SUMMARY_RES)
        self.assertEqual(recv["payload"]["summary"], summary_text)

    # =========================================================================
    # Bonus B3: Typing Indicator
    # =========================================================================

    def test_B3_typing_indicator_event(self):
        """B3: Verifies transmission and reception of TYPING status notifications."""
        rx_thread = self._start_receive_thread()

        self.client.send_packet(MSG_TYPING, {"room_type": "PRIVATE", "target": "Bob", "is_typing": True})
        sent = self._read_server_wire()
        self.assertEqual(sent["type"], MSG_TYPING)
        self.assertTrue(sent["payload"]["is_typing"])

        self._write_server_wire(MSG_TYPING, {"room_type": "PRIVATE", "from": "Bob", "is_typing": False})
        recv = self.incoming_queue.get(timeout=2.0)
        self.assertEqual(recv["type"], MSG_TYPING)
        self.assertFalse(recv["payload"]["is_typing"])

    # =========================================================================
    # Bonus B4: Push-to-Talk Voice Messaging
    # =========================================================================

    def test_B4_voice_message_transmission(self):
        """B4: Verifies sending and receiving Base64 voice audio payloads."""
        rx_thread = self._start_receive_thread()

        dummy_audio_b64 = "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="
        self.client.send_packet(MSG_VOICE_MSG, {"to": "Bob", "audio_data": dummy_audio_b64})

        sent = self._read_server_wire()
        self.assertEqual(sent["type"], MSG_VOICE_MSG)
        self.assertEqual(sent["payload"]["audio_data"], dummy_audio_b64)

        self._write_server_wire(MSG_VOICE_MSG, {"from": "Bob", "audio_data": dummy_audio_b64})
        recv = self.incoming_queue.get(timeout=2.0)
        self.assertEqual(recv["type"], MSG_VOICE_MSG)
        self.assertEqual(recv["payload"]["audio_data"], dummy_audio_b64)


if __name__ == "__main__":
    unittest.main()