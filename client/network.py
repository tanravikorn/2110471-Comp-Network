"""
Module: client/network.py
Purpose: Client TCP socket wrapper and background receiver thread.
"""

import queue
import socket
import threading
from typing import Optional, Tuple

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
    MSG_TYPING,
    MSG_VOICE_MSG,
    SocketLineBuffer,
    encode_message,
)


class NetworkClient:
    def __init__(self, incoming_queue: Optional[queue.Queue] = None) -> None:
        # The queue safely bridges the background socket thread to Tkinter/CLI code.
        self.sock: Optional[socket.socket] = None
        self.incoming_queue: queue.Queue = incoming_queue if incoming_queue is not None else queue.Queue()
        self.connected = False
        self.username: Optional[str] = None
        self._send_lock = threading.Lock()
        self.receive_thread: Optional[threading.Thread] = None

    def connect(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> Tuple[bool, str]:
        """Connect to the server and start the background TCP receiver (R1, R2)."""
        if self.connected:
            return True, "Already connected"

        sock = None
        try:
            # Use a timeout only while establishing the connection.
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((host, port))
            sock.settimeout(None)
            self.sock = sock
            self.connected = True
            self.receive_thread = threading.Thread(
                target=self._receive_loop,
                name="NetworkReceive",
                daemon=True,
            )
            self.receive_thread.start()
            return True, "Connected successfully"
        except (OSError, socket.timeout) as exc:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            return False, f"Connection failed: {exc}"

    def _receive_loop(self) -> None:
        """Read newline-delimited JSON packets and queue them for the GUI (R2)."""
        if self.sock is None:
            return

        # SocketLineBuffer handles fragmented TCP reads and sticky JSON packets.
        line_buffer = SocketLineBuffer(self.sock, BUFFER_SIZE)
        try:
            while self.connected:
                msg = line_buffer.read_message()
                self.incoming_queue.put(msg)
        except (EOFError, ConnectionResetError, ConnectionAbortedError, OSError):
            if self.connected:
                self.incoming_queue.put({"type": "DISCONNECTED", "payload": {}})
        finally:
            self.connected = False

    def send_packet(self, msg_type: str, payload: dict) -> bool:
        """Encode the standard envelope and send newline-framed UTF-8 bytes (R2)."""
        if not self.connected or self.sock is None:
            return False
        try:
            with self._send_lock:
                self.sock.sendall(encode_message(msg_type, payload))
            return True
        except (OSError, ConnectionError):
            self.disconnect()
            return False

    def disconnect(self) -> None:
        """Cleanly close the socket and clear the current username."""
        self.connected = False
        if self.sock is not None:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        self.username = None

    def send_register(self, username: str) -> bool:
        # R3: request server-side validation and uniqueness of the username.
        return self.send_packet(MSG_REGISTER, {"username": username})

    def send_private_message(self, target_user: str, text: str) -> bool:
        return self.send_packet(MSG_PRIVATE, {"to": target_user, "text": text})

    def send_create_group(self, group_name: str) -> bool:
        return self.send_packet(MSG_CREATE_GROUP, {"group": group_name})

    def send_join_group(self, group_name: str) -> bool:
        return self.send_packet(MSG_JOIN_GROUP, {"group": group_name})

    def send_group_message(self, group_name: str, text: str) -> bool:
        return self.send_packet(MSG_GROUP, {"group": group_name, "text": text})

    def send_typing(self, room_type: str, target: str, is_typing: bool) -> bool:
        return self.send_packet(MSG_TYPING, {
            "room_type": room_type,
            "target": target,
            "is_typing": is_typing,
        })

    def send_ai_summary_request(self, room_type: str, target: str) -> bool:
        return self.send_packet(MSG_AI_SUMMARY_REQ, {
            "room_type": room_type,
            "target": target,
        })

    def send_voice_message(self, room_type: str, target: str, audio_b64: str, duration: float) -> bool:
        return self.send_packet(MSG_VOICE_MSG, {
            "room_type": room_type,
            "target": target,
            "audio_b64": audio_b64,
            "duration": duration,
        })
