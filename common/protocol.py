"""
Module: common/protocol.py
Purpose: Shared Application-Layer Protocol Specification & TCP Framing Helpers
Mapped Requirements:
  - R1 (System Architecture): Defines the application-layer JSON protocol running on top of TCP/IP.
  - R2 (Socket Programming Only): Defines raw TCP byte-stream framing (newline-delimited UTF-8 JSON).
  - R3–R11 (Fundamental Features): Defines the 3-key Envelope (`type`, `timestamp`, `payload`),
    message type constants, error code constants, and payload structures.
  - B1, B3, B4 (Bonus Features): Defines `TYPING`, `AI_SUMMARY_REQ`, `AI_SUMMARY_RES`, and `VOICE_MSG`.
"""

import json
import socket
from datetime import datetime
from typing import Any, Dict, Generator, Optional, Union

# ==============================================================================
# 1. Network & Framing Constants (R1, R2)
# ==============================================================================
DEFAULT_HOST: str = "0.0.0.0"   # Bind to all network interfaces (LAN / Cloud VPS)
DEFAULT_PORT: int = 5000        # Default TCP port for chat server
ENCODING: str = "utf-8"         # Standard character encoding for all network packets
DELIMITER: str = "\n"           # Stream frame delimiter (newline separates JSON packets)
BUFFER_SIZE: int = 16384        # Chunk size for socket recv (16KB handles voice base64 smoothly)

# ==============================================================================
# 2. Standard JSON Envelope Keys & Room Type Constants
# ==============================================================================
KEY_TYPE: str = "type"
KEY_TIMESTAMP: str = "timestamp"
KEY_PAYLOAD: str = "payload"

ROOM_PRIVATE: str = "PRIVATE"
ROOM_GROUP: str = "GROUP"

# ==============================================================================
# 3. Fundamental Message Type Constants (Part 2: R3–R11)
# ==============================================================================
# Registration & Authentication (R3)
MSG_REGISTER: str = "REGISTER"
MSG_REGISTER_ACK: str = "REGISTER_ACK"

# Online User Directory (R4)
MSG_CLIENT_LIST: str = "CLIENT_LIST"

# Private 1-on-1 Messaging (R5, R6, R7)
MSG_PRIVATE: str = "PRIVATE_MSG"

# Group Lifecycle & Directory (R8, R9, R10)
MSG_CREATE_GROUP: str = "CREATE_GROUP"
MSG_GROUP_LIST: str = "GROUP_LIST"
MSG_JOIN_GROUP: str = "JOIN_GROUP"

# Group Chat Messaging (R5, R6, R11)
MSG_GROUP: str = "GROUP_MSG"

# Error Notification
MSG_ERROR: str = "ERROR"

# ==============================================================================
# 4. Bonus Feature Message Type Constants (Part 3: B1, B3, B4)
# ==============================================================================
# Real-Time Typing Indicator (B3)
MSG_TYPING: str = "TYPING"

# AI Chat History Summarization (B1)
MSG_AI_SUMMARY_REQ: str = "AI_SUMMARY_REQ"
MSG_AI_SUMMARY_RES: str = "AI_SUMMARY_RES"

# Push-to-Talk Voice Message (B4)
MSG_VOICE_MSG: str = "VOICE_MSG"

# ==============================================================================
# 5. Standard Error Codes (`payload["code"]` in `MSG_ERROR`)
# ==============================================================================
ERR_USERNAME_TAKEN: str = "USERNAME_TAKEN"    # R3: Username is empty or already in use
ERR_NOT_REGISTERED: str = "NOT_REGISTERED"    # R3: Client sent action before registering
ERR_USER_NOT_FOUND: str = "USER_NOT_FOUND"    # R7/B4: Target private user is offline
ERR_GROUP_EXISTS: str = "GROUP_EXISTS"        # R8: Group name already exists
ERR_GROUP_NOT_FOUND: str = "GROUP_NOT_FOUND"  # R10/R11: Target group does not exist
ERR_ALREADY_IN_GROUP: str = "ALREADY_IN_GROUP"# R10: User already joined the group
ERR_NOT_IN_GROUP: str = "NOT_IN_GROUP"        # R11: User tried acting in a non-joined group
ERR_AI_UNAVAILABLE: str = "AI_UNAVAILABLE"    # B1: AI API key missing or LLM failed
ERR_INVALID_PACKET: str = "INVALID_PACKET"    # Malformed JSON or missing keys


# ==============================================================================
# 6. Serialization & Envelope Helpers
# ==============================================================================
def get_current_timestamp() -> str:
    """Returns current local time formatted as 'HH:MM:SS'."""
    return datetime.now().strftime("%H:%M:%S")


def build_message(msg_type: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Constructs a standard 3-key envelope dictionary:
      {"type": msg_type, "timestamp": "HH:MM:SS", "payload": payload or {}}
    """
    return {
        KEY_TYPE: msg_type,
        KEY_TIMESTAMP: get_current_timestamp(),
        KEY_PAYLOAD: payload if payload is not None else {}
    }


def encode_message(msg_or_type: Union[str, Dict[str, Any]], payload: Optional[Dict[str, Any]] = None) -> bytes:
    """
    Encodes a message into newline-delimited UTF-8 JSON bytes ready for `sock.sendall()`.

    Can be called either as:
      encode_message("REGISTER", {"username": "Alice"})
    or:
      encode_message({"type": "REGISTER", "timestamp": "12:00:00", "payload": {...}})
    """
    if isinstance(msg_or_type, str):
        envelope = build_message(msg_or_type, payload)
    elif isinstance(msg_or_type, dict):
        envelope = dict(msg_or_type)
        if KEY_TIMESTAMP not in envelope:
            envelope[KEY_TIMESTAMP] = get_current_timestamp()
        if KEY_PAYLOAD not in envelope:
            envelope[KEY_PAYLOAD] = payload if payload is not None else {}
    else:
        raise TypeError(f"Expected str or dict for message, got {type(msg_or_type).__name__}")

    json_str = json.dumps(envelope, ensure_ascii=False)
    return (json_str + DELIMITER).encode(ENCODING)


def send_packet(sock: socket.socket, msg_type: str, payload: Optional[Dict[str, Any]] = None) -> bool:
    """Helper to encode and transmit a JSON packet over raw TCP socket."""
    try:
        sock.sendall(encode_message(msg_type, payload or {}))
        return True
    except (OSError, ConnectionError):
        return False


def decode_message(raw_line: str) -> Dict[str, Any]:
    """
    Parses a single newline-stripped JSON string and validates standard envelope structure.
    Raises json.JSONDecodeError or ValueError on malformed packets.
    """
    data = json.loads(raw_line)
    if not isinstance(data, dict):
        raise ValueError("Malformed packet: expected JSON object at top level")
    if KEY_TYPE not in data:
        raise ValueError("Malformed packet: missing 'type' key")
    if KEY_PAYLOAD not in data or not isinstance(data[KEY_PAYLOAD], dict):
        raise ValueError("Malformed packet: missing or non-dict 'payload' key")
    if KEY_TIMESTAMP not in data:
        data[KEY_TIMESTAMP] = get_current_timestamp()
    return data


# ==============================================================================
# 7. TCP Stream Line Buffer Helper (Stream Demarcation)
# ==============================================================================
class SocketLineBuffer:
    """
    Buffers byte chunks from a TCP socket stream (`sock.recv()`) and yields
    fully-assembled, newline-delimited JSON message dictionaries.

    Solves:
      1. Sticky Packets: Multiple JSON envelopes received in one `recv()` call.
      2. Packet Fragmentation: Large payloads (e.g. voice Base64) split across multiple `recv()` calls.
    """

    def __init__(self, sock: socket.socket, buffer_size: int = BUFFER_SIZE):
        self.sock = sock
        self.buffer_size = buffer_size
        self._buffer: str = ""

    def read_message(self) -> Dict[str, Any]:
        """
        Reads and returns the next complete JSON message dictionary.
        Blocks until a complete newline-terminated line is available.

        Raises:
          EOFError: When the socket is closed cleanly by peer (recv returns 0 bytes).
          ConnectionResetError / OSError: When connection drops unexpectedly.
        """
        while True:
            if DELIMITER in self._buffer:
                line, self._buffer = self._buffer.split(DELIMITER, 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    return decode_message(line)
                except (json.JSONDecodeError, ValueError) as err:
                    # Skip malformed line and continue waiting for valid lines
                    continue

            chunk = self.sock.recv(self.buffer_size)
            if not chunk:
                raise EOFError("TCP socket connection closed by peer")
            self._buffer += chunk.decode(ENCODING, errors="replace")

    def __iter__(self) -> Generator[Dict[str, Any], None, None]:
        """Allows iterating over incoming messages until socket disconnection."""
        while True:
            try:
                yield self.read_message()
            except EOFError:
                break
