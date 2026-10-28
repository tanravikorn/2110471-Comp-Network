"""
Module: common/protocol.py
Purpose: Shared Application-Layer Protocol Specification & TCP Framing Helpers
Mapped Requirements:
  - R1 (System Architecture): Defines the application-layer JSON protocol running on top of TCP/IP.
  - R2 (Socket Programming Only): Defines raw TCP byte-stream framing (newline-delimited UTF-8 JSON).
  - R3–R11: Defines message types and payload structures for all fundamental chat features.
"""

# ==============================================================================
# TODO 1: Define Network Defaults
# ==============================================================================
# - DEFAULT_HOST = "0.0.0.0" (for server binding across LAN interfaces)
# - DEFAULT_PORT = 5000 (or another unprivileged TCP port, e.g., 5555)
# - ENCODING = "utf-8"
# - DELIMITER = "\n" (used to frame individual JSON objects over the TCP stream)
# - BUFFER_SIZE = 4096

# ==============================================================================
# TODO 2: Define Message Type Constants (Client <-> Server)
# ==============================================================================
# - MSG_REGISTER       = "REGISTER"        # (R3) Client -> Server: request unique username
# - MSG_REGISTER_ACK   = "REGISTER_ACK"    # (R3) Server -> Client: accept/reject username
# - MSG_CLIENT_LIST    = "CLIENT_LIST"     # (R4) Server -> All: list of all connected client names
# - MSG_PRIVATE        = "PRIVATE_MSG"     # (R7) Client <-> Server: direct 1-to-1 text message
# - MSG_CREATE_GROUP   = "CREATE_GROUP"    # (R8) Client -> Server: create group (creator as sole member)
# - MSG_GROUP_LIST     = "GROUP_LIST"      # (R9) Server -> All: dict/list of all groups + their member lists
# - MSG_JOIN_GROUP     = "JOIN_GROUP"      # (R10) Client -> Server: self-join an existing group
# - MSG_GROUP          = "GROUP_MSG"       # (R11) Client <-> Server: text message to a joined group
# - MSG_ERROR          = "ERROR"           # Server -> Client: error notification

# ==============================================================================
# TODO 3: Implement JSON Serialization & Deserialization Helpers
# ==============================================================================
# - Function `encode_message(data: dict) -> bytes`:
#     Serialize `data` dict to a compact JSON string, append `DELIMITER` ("\n"),
#     and encode to UTF-8 bytes ready for `sock.sendall()`.
#
# - Function `decode_message(raw_line: str) -> dict`:
#     Parse a single newline-stripped JSON string back into a Python dictionary.

# ==============================================================================
# TODO 4: Implement TCP Stream Line-Buffer Helper
# ==============================================================================
# - Because TCP is a continuous byte stream (`SOCK_STREAM`), a single `recv()` may
#   contain partial JSON or multiple concatenated JSON messages.
# - Create a helper class or generator `SocketLineReader` (or function `send_json(sock, payload)`):
#     1. Maintain an internal string/bytes buffer per socket connection.
#     2. Read chunks via `sock.recv(BUFFER_SIZE)`.
#     3. Split buffer by `DELIMITER` ("\n"), yielding complete JSON dicts one by one
#        while keeping any incomplete trailing bytes in the buffer for the next `recv()`.
