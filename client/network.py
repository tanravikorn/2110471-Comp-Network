"""
Module: client/network.py
Purpose: Client TCP Socket Wrapper & Background Receiver Thread
Mapped Requirements:
  - R2 (Socket Programming Only): Uses `socket.socket(socket.AF_INET, socket.SOCK_STREAM)`
    to exchange JSON-framed packets with the server.
  - R3–R11: Provides helper methods to send registration, private messages, group creation,
    group join requests, and group messages, while queuing incoming server packets for the GUI.
"""

# ==============================================================================
# TODO 1: Define `NetworkClient` Class
# ==============================================================================
# - Attributes:
#     - `self.sock: socket.socket | None = None`
#     - `self.incoming_queue: queue.Queue = queue.Queue()` (thread-safe bridge to Tkinter)
#     - `self.connected: bool = False`
#     - `self.username: str | None = None`

# ==============================================================================
# TODO 2: Implement Connection & Background Listener Thread (R1, R2)
# ==============================================================================
# - `connect(host: str, port: int) -> tuple[bool, str]`:
#     Create TCP socket, connect to `(host, port)`, set `self.connected = True`,
#     and spawn a daemon `threading.Thread` running `self._receive_loop()`.
#
# - `_receive_loop() -> None`:
#     Continuously read newline-delimited JSON messages from `self.sock` using `common.protocol`.
#     Push each parsed dictionary `msg` into `self.incoming_queue.put(msg)`.
#     If the server disconnects or an exception occurs, push a disconnect event to `self.incoming_queue`.
#
# - `disconnect() -> None`:
#     Close `self.sock` cleanly and set `self.connected = False`.

# ==============================================================================
# TODO 3: Implement Outgoing Action Methods (R3, R7, R8, R10, R11)
# ==============================================================================
# - `send_register(username: str) -> None`:
#     Send `{"type": MSG_REGISTER, "username": username}` (R3).
#
# - `send_private_message(target_user: str, text: str) -> None`:
#     Send `{"type": MSG_PRIVATE, "to": target_user, "text": text}` (R7).
#
# - `send_create_group(group_name: str) -> None`:
#     Send `{"type": MSG_CREATE_GROUP, "group": group_name}` (R8).
#
# - `send_join_group(group_name: str) -> None`:
#     Send `{"type": MSG_JOIN_GROUP, "group": group_name}` (R10).
#
# - `send_group_message(group_name: str, text: str) -> None`:
#     Send `{"type": MSG_GROUP, "group": group_name, "text": text}` (R11).
