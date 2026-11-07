"""
Module: server/client_handler.py
Purpose: Per-Client TCP Socket Connection & Request Router
Mapped Requirements:
  - R2 (TCP Socket Stream): Receives newline-delimited JSON packets via SocketLineBuffer.
  - R3–R11: Routes actions to modular handlers in server/handlers/.
  - B3 (Typing Indicator): Routes MSG_TYPING to handle_typing.
  - B4 (Voice Message): Routes MSG_VOICE_MSG to handle_voice_msg.
"""

import logging
import socket
from typing import Any, Dict, Optional, Tuple

from common.protocol import (
    ERR_NOT_REGISTERED,
    KEY_PAYLOAD,
    KEY_TYPE,
    MSG_CLIENT_LIST,
    MSG_CREATE_GROUP,
    MSG_ERROR,
    MSG_GROUP,
    MSG_JOIN_GROUP,
    MSG_PRIVATE,
    MSG_REGISTER,
    MSG_TYPING,
    MSG_VOICE_MSG,
    SocketLineBuffer,
    build_message,
    send_packet,
)
from server.handlers import (
    broadcast_client_list,
    broadcast_group_list,
    handle_create_group,
    handle_group_msg,
    handle_join_group,
    handle_private_msg,
    handle_register,
    handle_typing,
    handle_voice_msg,
)
from server.state import ServerState

logger = logging.getLogger("server.client_handler")


def handle_client(
    client_sock: socket.socket,
    client_addr: Tuple[str, int],
    state: ServerState,
) -> None:
    """
    Handles a single client's raw TCP socket connection.
    Routes incoming JSON actions to modular handlers in server/handlers/.
    """
    session: Dict[str, Any] = {"username": None}
    addr_str = f"{client_addr[0]}:{client_addr[1]}"
    logger.info(f"New client connected from {addr_str}")

    # Send initial online directory upon connection (R4)
    send_packet(client_sock, MSG_CLIENT_LIST, {"clients": state.get_client_list()})

    line_buffer = SocketLineBuffer(client_sock)

    try:
        for msg in line_buffer:
            msg_type = msg.get(KEY_TYPE, "UNKNOWN")
            payload = msg.get(KEY_PAYLOAD, {})
            logger.info(f"[{addr_str}] Action: {msg_type} | Payload: {payload}")

            # ------------------------------------------------------------------
            # Modular Action Routing
            # ------------------------------------------------------------------
            # 1. Registration (R3)
            if msg_type == MSG_REGISTER:
                handle_register(client_sock, payload, state, session)

            # All other actions require active registration
            elif not session.get("username"):
                send_packet(client_sock, MSG_ERROR, {
                    "code": ERR_NOT_REGISTERED,
                    "message": "You must register a username first via REGISTER",
                })

            # 2. Private 1-on-1 Messaging (R7)
            elif msg_type == MSG_PRIVATE:
                handle_private_msg(client_sock, payload, state, session)

            # 3. Create Group (R8)
            elif msg_type == MSG_CREATE_GROUP:
                handle_create_group(client_sock, payload, state, session)

            # 4. Join Group (R10)
            elif msg_type == MSG_JOIN_GROUP:
                handle_join_group(client_sock, payload, state, session)

            # 5. Group Chat Messaging (R11)
            elif msg_type == MSG_GROUP:
                handle_group_msg(client_sock, payload, state, session)

            # 6. Real-Time Typing Indicator (B3)
            elif msg_type == MSG_TYPING:
                handle_typing(client_sock, payload, state, session)

            # 7. Push-to-Talk Voice Message (B4)
            elif msg_type == MSG_VOICE_MSG:
                handle_voice_msg(client_sock, payload, state, session)

            # 8. Fallback / Future Actions
            else:
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
            broadcast_group_list(state)

        try:
            client_sock.close()
        except OSError:
            pass
        logger.info(f"Socket closed for {addr_str}")
