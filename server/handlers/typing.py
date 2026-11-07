"""
Module: server/handlers/typing.py
Purpose: Action Handler for MSG_TYPING (Bonus B3 / Special 3)
Mapped Requirements:
  - B3 (Real-Time Typing Indicator): Relays typing state (is_typing: bool)
    to target user (1-on-1 private chat) or multicast to group members
    excluding the sender (group chat).
"""

import logging
import socket
from typing import Any, Dict

from common.protocol import (
    MSG_TYPING,
    ROOM_GROUP,
    ROOM_PRIVATE,
    send_packet,
)
from server.state import ServerState

logger = logging.getLogger("server.handlers.typing")


def handle_typing(
    client_sock: socket.socket,
    payload: Dict[str, Any],
    state: ServerState,
    session: Dict[str, Any],
) -> bool:
    """
    Handles real-time typing indicators for private and group chats (B3).
    Relays typing status to peer(s) without echoing back to the sender.
    """
    sender = session.get("username", "")
    room_type = str(payload.get("room_type") or ROOM_PRIVATE).strip().upper()
    target = str(payload.get("target") or "").strip()
    is_typing = payload.get("is_typing") is True

    if not target:
        return False

    typing_payload = {
        "room_type": room_type,
        "target": target,
        "from": sender,
        "is_typing": is_typing,
    }

    if room_type == ROOM_PRIVATE:
        target_sock = state.get_client_socket(target)
        if not target_sock:
            logger.debug(f"Typing relay skipped: private recipient '{target}' is offline")
            return False

        # Deliver to recipient if not self
        if target_sock != client_sock:
            send_packet(target_sock, MSG_TYPING, typing_payload)
            logger.debug(f"Relayed private typing ({is_typing}) from '{sender}' to '{target}'")
        return True

    elif room_type == ROOM_GROUP:
        # Multicast to all members in group excluding sender
        member_socks = state.get_group_member_sockets(target, sender, exclude_sender=True)
        if not member_socks:
            logger.debug(f"Typing relay skipped: group '{target}' empty or '{sender}' not a member")
            return False

        for sock in member_socks:
            send_packet(sock, MSG_TYPING, typing_payload)

        logger.debug(f"Relayed group typing ({is_typing}) from '{sender}' to {len(member_socks)} members in '{target}'")
        return True

    else:
        logger.warning(f"Unknown room_type in TYPING packet: '{room_type}'")
        return False
