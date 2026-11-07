"""
Module: server/handlers/private_msg.py
Purpose: Action Handler for MSG_PRIVATE (R7)
Mapped Requirements:
  - R7 (Private Message Routing): Looks up receiver socket, unicasts message,
    echoes copy to sender, and returns error if target is offline.
  - B1 (AI Summary History): Records successful messages into room history.
"""

import logging
import socket
from typing import Any, Dict

from common.protocol import (
    ERR_USER_NOT_FOUND,
    MSG_ERROR,
    MSG_PRIVATE,
    get_current_timestamp,
    send_packet,
)
from server.state import ServerState, get_private_room_key

logger = logging.getLogger("server.handlers.private_msg")


def handle_private_msg(
    client_sock: socket.socket,
    payload: Dict[str, Any],
    state: ServerState,
    session: Dict[str, Any],
) -> bool:
    """
    Handles 1-on-1 private chat messaging (R7).
    Unicasts message to target receiver and echoes copy to sender.
    If target is offline or not found, returns ERR_USER_NOT_FOUND error.
    Records message to ServerState room history (B1).
    """
    sender = session.get("username")
    target = str(payload.get("to", "")).strip()
    text = str(payload.get("text", "")).strip()

    if not text:
        return False

    target_sock = state.get_client_socket(target)
    if not target_sock:
        logger.warning(f"Private message failed: User '{target}' is offline")
        send_packet(client_sock, MSG_ERROR, {
            "code": ERR_USER_NOT_FOUND,
            "message": f"User '{target}' is offline or does not exist"
        })
        return False

    msg_payload = {
        "from": sender,
        "to": target,
        "text": text,
    }

    # 1. Unicast to recipient
    send_packet(target_sock, MSG_PRIVATE, msg_payload)

    # 2. Echo to sender (if recipient is not self)
    if target_sock != client_sock:
        send_packet(client_sock, MSG_PRIVATE, msg_payload)

    # 3. Record in room history for AI Summarization (B1)
    timestamp = get_current_timestamp()
    room_key = get_private_room_key(sender, target)
    state.record_message(room_key, sender, text, timestamp)

    logger.info(f"Private message routed from '{sender}' to '{target}'")
    return True
