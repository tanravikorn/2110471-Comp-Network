"""
Module: server/client_handler.py
Purpose: Per-Client TCP Socket Connection & Request Router
"""

import logging
import socket
from typing import Any, Dict, Optional, Tuple

from common.protocol import (
    ERR_NOT_REGISTERED,
    KEY_PAYLOAD,
    KEY_TYPE,
    MSG_ERROR,
    MSG_REGISTER,
    SocketLineBuffer,
    build_message,
    encode_message,
)
from server.handlers.register import broadcast_client_list, handle_register
from server.state import ServerState

logger = logging.getLogger("server.client_handler")


def send_packet(sock: socket.socket, msg_type: str, payload: Optional[Dict[str, Any]] = None) -> bool:
    """Helper to encode and transmit a JSON packet over raw TCP socket."""
    try:
        wire_bytes = encode_message(msg_type, payload or {})
        sock.sendall(wire_bytes)
        return True
    except (OSError, ConnectionError):
        return False


def handle_client(
    client_sock: socket.socket,
    client_addr: Tuple[str, int],
    state: ServerState,
) -> None:
    """
    Handles a single client's raw TCP socket connection.
    Routes incoming JSON actions to their respective modular handlers in server/handlers/.
    """

    session: Dict[str, Any] = {"username": None}
    addr_str = f"{client_addr[0]}:{client_addr[1]}"
    logger.info(f"New client connected from {addr_str}")

    line_buffer = SocketLineBuffer(client_sock)

    try:
        for msg in line_buffer:
            msg_type = msg.get(KEY_TYPE, "UNKNOWN")
            payload = msg.get(KEY_PAYLOAD, {})
            logger.info(f"[{addr_str}] Action: {msg_type} | Payload: {payload}")

            # ------------------------------------------------------------------
            # Modular Action Routing
            # ------------------------------------------------------------------
            # 1. Action: REGISTER (R3 & R4)
            if msg_type == MSG_REGISTER:
                handle_register(client_sock, payload, state, session)

            # Future handlers (PRIVATE_MSG, GROUP_MSG, etc.) will be added here
            else:
                if not session.get("username"):
                    send_packet(client_sock, MSG_ERROR, {
                        "code": ERR_NOT_REGISTERED,
                        "message": "You must register a username first via REGISTER"
                    })
                else:
                    # Echo response for actions whose handlers are not yet wired
                    response = build_message(
                        msg_type="RESPONSE",
                        payload={
                            "status": "OK",
                            "echo_type": msg_type,
                            "echo_payload": payload,
                        },
                    )
                    send_packet(client_sock, response[KEY_TYPE], response[KEY_PAYLOAD])

    except (EOFError, ConnectionError):
        logger.info(f"Client disconnected: {session.get('username') or addr_str}")
    except Exception as exc:
        logger.error(f"Error handling client {addr_str}: {exc}", exc_info=True)
    finally:
        # Cleanup state upon disconnect
        registered_user = session.get("username")
        if registered_user:
            state.remove_client(registered_user)
            logger.info(f"Removed '{registered_user}' from state on disconnect")
            broadcast_client_list(state)

        try:
            client_sock.close()
        except OSError:
            pass
        logger.info(f"Socket closed for {addr_str}")
