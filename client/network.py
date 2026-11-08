"""
Module: client/network.py
Purpose: Client TCP Socket Wrapper & Background Receiver Thread (R2-R11, B1, B3, B4)
"""
import queue
import socket
import threading
from typing import Any, Dict, Optional, Tuple

from common.protocol import (
    BUFFER_SIZE,
    DEFAULT_HOST,
    DEFAULT_PORT,
    MSG_AI_SUMMARY_REQ,
    MSG_CREATE_GROUP,
    MSG_GROUP,
    MSG_JOIN_GROUP,
    MSG_PRIVATE,
    MSG_REGISTER,
    GET_HISTORY,
    MSG_TYPING,
    MSG_VOICE_MSG,
    SocketLineBuffer,
    encode_message,
)


class NetworkClient:
    def __init__(self, incoming_queue: Optional[queue.Queue] = None):
        self.sock: Optional[socket.socket] = None
        self.incoming_queue: queue.Queue = incoming_queue if incoming_queue is not None else queue.Queue()
        self.connected: bool = False
        self.username: Optional[str] = None
        self.receive_thread: Optional[threading.Thread] = None

    def connect(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> Tuple[bool, str]:
        """Creates a raw TCP socket connection and launches background receiver thread (R2)."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((host, port))
            self.connected = True
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.receive_thread.start()
            return True, "Connected successfully"
        except Exception as e:
            self.disconnect()
            return False, f"Connection failed: {e}"

    def _receive_loop(self) -> None:
        """Reads raw byte stream from socket and demuxes newline-delimited JSON packets (R2)."""
        if not self.sock:
            return
        line_buffer = SocketLineBuffer(self.sock, BUFFER_SIZE)
        while self.connected:
            try:
                msg = line_buffer.read_message()
                self.incoming_queue.put(msg)
            except (EOFError, ConnectionResetError, OSError):
                break

        self.connected = False
        self.incoming_queue.put({"type": "DISCONNECTED", "payload": {}})

    def disconnect(self) -> None:
        """Closes TCP socket cleanly (R2)."""
        self.connected = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def send_packet(self, msg_type: str, payload: dict) -> None:
        """Encodes JSON envelope and transmits raw bytes over socket via sendall() (R2)."""
        if not self.connected or not self.sock:
            return
        try:
            wire_data = encode_message(msg_type, payload)
            self.sock.sendall(wire_data)
        except Exception:
            self.disconnect()

    def send_register(self, username: str) -> None:
        """Sends MSG_REGISTER with unique username payload (R3)."""
        self.username = username
        self.send_packet(MSG_REGISTER, {"username": username})

    def send_private_message(self, target_user: str, text: str) -> None:
        """Transmits 1-on-1 private message (R7)."""
        self.send_packet(MSG_PRIVATE, {"to": target_user, "text": text})

    def send_create_group(self, group_name: str) -> None:
        """Transmits group creation packet (R8)."""
        self.send_packet(MSG_CREATE_GROUP, {"group": group_name})

    def send_join_group(self, group_name: str) -> None:
        """Transmits group self-join packet (R10)."""
        self.send_packet(MSG_JOIN_GROUP, {"group": group_name})

    def send_group_message(self, group_name: str, text: str) -> None:
        """Transmits group room message packet (R11)."""
        self.send_packet(MSG_GROUP, {"group": group_name, "text": text})

    def send_get_history(self, room_type: str, target: str) -> None:
        """Requests recorded chat history for a private or group room."""
        self.send_packet(GET_HISTORY, {"room_type": room_type, "target": target})

    def send_typing(self, room_type: str, target: str, is_typing: bool) -> None:
        """Transmits typing status packet (B3)."""
        self.send_packet(MSG_TYPING, {"room_type": room_type, "target": target, "is_typing": is_typing})

    def send_ai_summary_request(self, room_type: str, target: str) -> None:
        """Transmits AI conversation summary request packet (B1)."""
        self.send_packet(MSG_AI_SUMMARY_REQ, {"room_type": room_type, "target": target})

    def send_voice_message(self, room_type: str, target: str, audio_b64: str, duration: float) -> None:
        """Transmits push-to-talk voice clip packet (B4)."""
        self.send_packet(MSG_VOICE_MSG, {"room_type": room_type, "target": target, "audio_b64": audio_b64, "duration": duration})