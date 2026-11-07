"""
Unit & Integration Tests for AI Conversation Summary (Bonus B1)
Verifies:
  - .env parsing (load_env_file)
  - Prompt formatting & offline heuristic fallback
  - ServerState chat history buffering & sliding limit
  - handle_ai_summary packet validation & permissions
  - Async dispatch of AI_SUMMARY_RES
"""

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from common.protocol import (
    ERR_AI_UNAVAILABLE,
    ERR_GROUP_NOT_FOUND,
    ERR_INVALID_PACKET,
    ERR_NOT_IN_GROUP,
    KEY_PAYLOAD,
    KEY_TYPE,
    MSG_AI_SUMMARY_RES,
    MSG_ERROR,
    ROOM_GROUP,
    ROOM_PRIVATE,
    decode_message,
)
from server.ai_service import (
    format_history_for_prompt,
    generate_chat_summary,
    generate_fallback_summary,
    load_env_file,
)
from server.handlers.ai_summary import handle_ai_summary
from server.state import ServerState, get_group_room_key, get_private_room_key


class TestAIService(unittest.TestCase):
    """Tests for server/ai_service.py functions."""

    def test_load_env_file(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(os.environ, {}, clear=True):
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "# Comment line\n"
                "TEST_AI_KEY=ai_secret_12345\n"
                "QUOTED_VAL=\"hello world\"\n"
                "EMPTY_VAL=\n"
                "INVALID LINE WITHOUT EQUALS\n",
                encoding="utf-8",
            )
            load_env_file(env_path)
            self.assertEqual(os.environ.get("TEST_AI_KEY"), "ai_secret_12345")
            self.assertEqual(os.environ.get("QUOTED_VAL"), "hello world")

    def test_format_history_for_prompt(self):
        history = [
            {"timestamp": "10:00:01", "sender": "Alice", "text": "Hi Bob"},
            {"timestamp": "10:00:05", "sender": "Bob", "text": "Let's do networks"},
        ]
        prompt = format_history_for_prompt("StudyRoom", history)
        self.assertIn("StudyRoom", prompt)
        self.assertIn("[10:00:01] Alice: Hi Bob", prompt)
        self.assertIn("[10:00:05] Bob: Let's do networks", prompt)

    def test_generate_fallback_summary(self):
        history = [
            {"timestamp": "10:00:01", "sender": "Alice", "text": "Deploying VPS"},
            {"timestamp": "10:00:05", "sender": "Bob", "text": "Port 5000 is open"},
        ]
        summary = generate_fallback_summary("Group1", history)
        self.assertIn("Room: Group1", summary)
        self.assertIn("Total Messages: 2", summary)
        self.assertIn("Alice", summary)
        self.assertIn("Bob", summary)

    def test_generate_chat_summary_empty_history(self):
        success, msg = generate_chat_summary("Group1", [])
        self.assertFalse(success)
        self.assertIn("No chat messages", msg)

    @patch("server.ai_service.get_api_key", return_value="")
    def test_generate_chat_summary_no_key_fallback(self, mock_key):
        history = [{"timestamp": "10:00:01", "sender": "Alice", "text": "Hello"}]
        success, summary = generate_chat_summary("Group1", history)
        self.assertTrue(success)
        self.assertIn("[AI Summary - Offline Mode]", summary)

    @patch("server.ai_service.get_api_key", return_value="dummy_valid_key")
    @patch("urllib.request.urlopen")
    def test_generate_chat_summary_gemini_api_success(self, mock_urlopen, mock_key):
        history = [{"timestamp": "10:00:01", "sender": "Alice", "text": "Let's finish the project"}]
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "candidates": [{
                "content": {
                    "parts": [{"text": "Summary: Finished computer network project."}]
                }
            }]
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        success, summary = generate_chat_summary("Room1", history)
        self.assertTrue(success)
        self.assertEqual(summary, "Summary: Finished computer network project.")

        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_header("X-goog-api-key"), "dummy_valid_key")
        self.assertNotIn("dummy_valid_key", req.full_url)


class TestServerStateHistory(unittest.TestCase):
    """Tests for ServerState chat history buffering."""

    def setUp(self):
        self.state = ServerState()

    def test_canonical_room_keys(self):
        self.assertEqual(get_private_room_key("Alice", "Bob"), "PRIVATE:Alice:Bob")
        self.assertEqual(get_private_room_key("Bob", "Alice"), "PRIVATE:Alice:Bob")
        self.assertEqual(get_group_room_key("TeamAlpha"), "GROUP:TeamAlpha")

    def test_record_and_get_history(self):
        key = get_private_room_key("Alice", "Bob")
        self.state.record_message(key, "Alice", "Hey", "12:00:00")
        self.state.record_message(key, "Bob", "Hello!", "12:00:05")

        history = self.state.get_room_history(key)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["sender"], "Alice")
        self.assertEqual(history[1]["sender"], "Bob")

    def test_sliding_window_limit(self):
        key = get_group_room_key("SpamRoom")
        for i in range(60):
            self.state.record_message(key, f"User{i}", f"Msg {i}", "12:00:00", max_history=50)

        history = self.state.get_room_history(key)
        self.assertEqual(len(history), 50)
        self.assertEqual(history[0]["sender"], "User10")
        self.assertEqual(history[-1]["sender"], "User59")


class TestAIHandler(unittest.TestCase):
    """Tests for server/handlers/ai_summary.py."""

    def setUp(self):
        self.state = ServerState()
        self.client_sock = MagicMock()
        self.peer_sock = MagicMock()
        self.session = {"username": "Alice"}
        self.state.register_client("Alice", self.client_sock)
        self.state.register_client("Bob", self.peer_sock)

    def test_invalid_payload(self):
        result = handle_ai_summary(self.client_sock, {}, self.state, self.session)
        self.assertFalse(result)
        sent = self.client_sock.sendall.call_args[0][0].decode("utf-8")
        packet = decode_message(sent)
        self.assertEqual(packet[KEY_TYPE], MSG_ERROR)
        self.assertEqual(packet[KEY_PAYLOAD]["code"], ERR_INVALID_PACKET)

    def test_group_summary_not_found(self):
        payload = {"room_type": ROOM_GROUP, "target": "GhostGroup"}
        result = handle_ai_summary(self.client_sock, payload, self.state, self.session)
        self.assertFalse(result)
        sent = self.client_sock.sendall.call_args[0][0].decode("utf-8")
        packet = decode_message(sent)
        self.assertEqual(packet[KEY_TYPE], MSG_ERROR)
        self.assertEqual(packet[KEY_PAYLOAD]["code"], ERR_GROUP_NOT_FOUND)

    def test_group_summary_not_in_group(self):
        self.state.create_group("SecretGroup", "Bob")
        payload = {"room_type": ROOM_GROUP, "target": "SecretGroup"}
        result = handle_ai_summary(self.client_sock, payload, self.state, self.session)
        self.assertFalse(result)
        sent = self.client_sock.sendall.call_args[0][0].decode("utf-8")
        packet = decode_message(sent)
        self.assertEqual(packet[KEY_TYPE], MSG_ERROR)
        self.assertEqual(packet[KEY_PAYLOAD]["code"], ERR_NOT_IN_GROUP)

    def test_empty_history_error(self):
        self.state.create_group("EmptyGroup", "Alice")
        payload = {"room_type": ROOM_GROUP, "target": "EmptyGroup"}
        result = handle_ai_summary(self.client_sock, payload, self.state, self.session)
        self.assertFalse(result)
        sent = self.client_sock.sendall.call_args[0][0].decode("utf-8")
        packet = decode_message(sent)
        self.assertEqual(packet[KEY_TYPE], MSG_ERROR)
        self.assertEqual(packet[KEY_PAYLOAD]["code"], ERR_AI_UNAVAILABLE)

    def test_duplicate_in_flight_rejected(self):
        key = get_private_room_key("Alice", "Bob")
        self.state.record_message(key, "Alice", "Project done", "12:00:00")
        self.assertTrue(self.state.try_acquire_summary(key))

        payload = {"room_type": ROOM_PRIVATE, "target": "Bob"}
        self.assertFalse(handle_ai_summary(self.client_sock, payload, self.state, self.session))
        self.state.release_summary(key)

    @patch("server.ai_service.get_api_key", return_value="")
    def test_successful_summary_dispatch(self, _mock_key):
        key = get_private_room_key("Alice", "Bob")
        self.state.record_message(key, "Alice", "Project done", "12:00:00")
        self.state.record_message(key, "Bob", "Great job!", "12:00:05")

        done = threading.Event()
        self.peer_sock.sendall.side_effect = lambda _data: done.set()

        payload = {"room_type": ROOM_PRIVATE, "target": "Bob"}
        result = handle_ai_summary(self.client_sock, payload, self.state, self.session)
        self.assertTrue(result)
        self.assertTrue(done.wait(timeout=1.0))

        sent = self.client_sock.sendall.call_args[0][0].decode("utf-8")
        packet = decode_message(sent)
        self.assertEqual(packet[KEY_TYPE], MSG_AI_SUMMARY_RES)
        self.assertEqual(packet[KEY_PAYLOAD]["room_type"], ROOM_PRIVATE)
        self.assertEqual(packet[KEY_PAYLOAD]["target"], "Bob")
        self.assertEqual(packet[KEY_PAYLOAD]["requested_by"], "Alice")
        self.assertIn("summary", packet[KEY_PAYLOAD])


if __name__ == "__main__":
    unittest.main()
