"""
Module: server/handlers/register.py
Purpose: Action Handler for MSG_REGISTER
Mapped Requirements:
  - R3 (Unique Client Name): Validates and registers a unique username.
  - R4 (Online Client Directory): Broadcasts updated CLIENT_LIST to all clients upon successful registration.
"""

import logging
import socket
from typing import Any, Dict

from common.protocol import (
    MSG_CLIENT_LIST,
    MSG_REGISTER_ACK,
    encode_message,
)
from server.state import ServerState

logger = logging.getLogger("server.handlers.register")


def send_packet(sock: socket.socket, msg_type: str, payload: Dict[str, Any]) -> bool:
    """Helper to encode and transmit a JSON packet over raw TCP socket."""
    try:
        sock.sendall(encode_message(msg_type, payload))
        return True
    except (OSError, ConnectionError):
        return False


def broadcast_client_list(state: ServerState) -> None:
    """Broadcasts current online usernames list to all connected clients (R4)."""
    clients = state.get_client_list()
    payload = {"clients": clients}
    for sock in state.get_all_client_sockets():
        send_packet(sock, MSG_CLIENT_LIST, payload)


def handle_register(
    client_sock: socket.socket,
    payload: Dict[str, Any],
    state: ServerState,
    session: Dict[str, Any],
) -> bool:
    """
    Processes a REGISTER request from a client socket (R3).

    Args:
        client_sock: The connecting client's TCP socket.
        payload: Dict containing {"username": "<str>"}.
        state: The shared ServerState registry.
        session: Per-connection session dictionary tracking {"username": ...}.

    Returns:
        bool: True if registration succeeded, False otherwise.
    """
    if session.get("username"):
        send_packet(client_sock, MSG_REGISTER_ACK, {
            "success": False,
            "message": f"Already registered as '{session['username']}'"
        })
        return False

    requested_name = str(payload.get("username", "")).strip()

    # 1. Validate empty username
    if not requested_name:
        logger.warning("Rejected registration: empty username")
        send_packet(client_sock, MSG_REGISTER_ACK, {
            "success": False,
            "message": "Username cannot be empty"
        })
        return False

    # 2. Check uniqueness in ServerState (R3)
    if state.register_client(requested_name, client_sock):
        session["username"] = requested_name
        logger.info(f"Registered new client: '{requested_name}'")

        # Send affirmative ACK
        send_packet(client_sock, MSG_REGISTER_ACK, {
            "success": True,
            "message": f"Welcome, {requested_name}!"
        })

        # Broadcast updated client directory to all connected clients (R4)
        broadcast_client_list(state)
        return True
    else:
        logger.warning(f"Rejected registration: '{requested_name}' is already taken")
        send_packet(client_sock, MSG_REGISTER_ACK, {
            "success": False,
            "message": f"Username '{requested_name}' is already taken"
        })
        return False
