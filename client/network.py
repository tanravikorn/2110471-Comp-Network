"""
Module: client/network.py
Purpose: Client TCP Socket Wrapper & Background Receiver Thread
Mapped Requirements:
  - R2 (Socket Programming Only): Uses `socket.socket(socket.AF_INET, socket.SOCK_STREAM)`
    to exchange newline-delimited JSON envelopes (`type`, `timestamp`, `payload`) with the server.
  - R3–R11 (Fundamental): Sends registration, private messages, group creation/join, and group messages.
  - B1, B3, B4 (Bonus): Sends typing indicator updates (`TYPING`), AI summary requests (`AI_SUMMARY_REQ`),
    and Base64 WAV voice clips (`VOICE_MSG`), while queuing incoming server packets for the GUI.
"""

import queue
import socket
import threading
from typing import Optional

from common.protocol import (
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
    def __init__(self) -> None:
        # Keep the socket state and the GUI-safe incoming queue together for the whole client lifetime.
        self.sock: Optional[socket.socket] = None
        self.incoming_queue: queue.Queue = queue.Queue()
        self.connected = False
        self.username: Optional[str] = None
        # Multiple GUI actions must not send partial or interleaved TCP writes.
        self._send_lock = threading.Lock()
        self._receive_thread: Optional[threading.Thread] = None

    def connect(self, host: str, port: int) -> tuple[bool, str]:
        if self.connected:
            return True, "Already connected"

        sock = None
        try:
            # Use a short timeout only while connecting; otherwise the receiver should wait normally.
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((host, port))
            sock.settimeout(None)
            self.sock = sock
            self.connected = True
            # Reading happens on a daemon thread so incoming packets never block the Tkinter UI.
            self._receive_thread = threading.Thread(
                target=self._receive_loop,
                name="NetworkReceive",
                daemon=True,
            )
            self._receive_thread.start()
            return True, "Connected"
        except (OSError, socket.timeout) as exc:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            return False, str(exc)

    def _receive_loop(self) -> None:
        if self.sock is None:
            return

        # SocketLineBuffer handles packet fragmentation and multiple JSON packets in one TCP chunk.
        line_buffer = SocketLineBuffer(self.sock)
        try:
            while self.connected:
                msg = line_buffer.read_message()
                # GUI windows poll this queue instead of directly touching Tkinter from the socket thread.
                self.incoming_queue.put(msg)
        except (EOFError, ConnectionResetError, ConnectionAbortedError, OSError):
            if self.connected:
                self.incoming_queue.put({"type": "DISCONNECT", "timestamp": "", "payload": {}})
        finally:
            self.connected = False

    def _send(self, msg_type: str, payload: dict) -> bool:
        if not self.connected or self.sock is None:
            return False
        try:
            with self._send_lock:
                # encode_message adds the protocol envelope and newline framing before sendall().
                self.sock.sendall(encode_message(msg_type, payload))
            return True
        except (OSError, ConnectionError):
            self.connected = False
            return False

    def disconnect(self) -> None:
        # Stop the receive loop first, then close the socket and clear this session's username.
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
        # R3 handshake: ask the server whether this username is available before opening the lobby.
        return self._send(MSG_REGISTER, {"username": username})

    def send_private_message(self, target_user: str, text: str) -> bool:
        return self._send(MSG_PRIVATE, {"to": target_user, "text": text})

    def send_create_group(self, group_name: str) -> bool:
        return self._send(MSG_CREATE_GROUP, {"group": group_name})

    def send_join_group(self, group_name: str) -> bool:
        return self._send(MSG_JOIN_GROUP, {"group": group_name})

    def send_group_message(self, group_name: str, text: str) -> bool:
        return self._send(MSG_GROUP, {"group": group_name, "text": text})

    def send_typing(self, room_type: str, target: str, is_typing: bool) -> bool:
        return self._send(MSG_TYPING, {"room_type": room_type, "target": target, "is_typing": is_typing})

    def send_ai_summary_request(self, room_type: str, target: str) -> bool:
        return self._send(MSG_AI_SUMMARY_REQ, {"room_type": room_type, "target": target})

    def send_voice_message(self, room_type: str, target: str, audio_b64: str, duration: float) -> bool:
        return self._send(MSG_VOICE_MSG, {
            "room_type": room_type,
            "target": target,
            "audio_b64": audio_b64,
            "duration": duration,
        })
