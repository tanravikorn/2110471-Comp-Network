"""
Module: server/handlers/group.py
Purpose: Action Handlers for Group Lifecycle & Messaging (R8, R9, R10, R11)
Mapped Requirements:
  - R8 (Create Group): Creates group with creator as sole member.
  - R9 (Group List Directory): Broadcasts all groups and member lists to all clients.
  - R10 (Self-Join Group): Allows users to explicitly join existing groups.
  - R11 (Group Chat Routing): Multicasts messages only to members of the target group.
"""

import logging
import socket
from typing import Any, Dict

from common.protocol import (
    ERR_ALREADY_IN_GROUP,
    ERR_GROUP_EXISTS,
    ERR_GROUP_NOT_FOUND,
    ERR_NOT_IN_GROUP,
    MSG_ERROR,
    MSG_GROUP,
    MSG_GROUP_LIST,
    send_packet,
)
from server.state import ServerState

logger = logging.getLogger("server.handlers.group")


def broadcast_group_list(state: ServerState) -> None:
    """Broadcasts all groups and their current members to all connected clients (R9)."""
    groups = state.get_groups_with_members()
    payload = {"groups": groups}
    for sock in state.get_all_client_sockets():
        send_packet(sock, MSG_GROUP_LIST, payload)


def handle_create_group(
    client_sock: socket.socket,
    payload: Dict[str, Any],
    state: ServerState,
    session: Dict[str, Any],
) -> bool:
    """
    Creates a new chat group with creator as initial member (R8).
    Broadcasts updated GROUP_LIST upon success (R9).
    """
    group_name = str(payload.get("group", "")).strip()
    sender = session.get("username", "")

    success, msg = state.create_group(group_name, sender)
    if not success:
        logger.warning(f"Create group failed: {msg}")
        send_packet(client_sock, MSG_ERROR, {
            "code": ERR_GROUP_EXISTS,
            "message": msg,
        })
        return False

    logger.info(f"Group '{group_name}' created by '{sender}'")
    broadcast_group_list(state)
    return True


def handle_join_group(
    client_sock: socket.socket,
    payload: Dict[str, Any],
    state: ServerState,
    session: Dict[str, Any],
) -> bool:
    """
    Adds requesting client to an existing group (R10).
    Broadcasts updated GROUP_LIST upon success (R9).
    """
    group_name = str(payload.get("group", "")).strip()
    sender = session.get("username", "")

    success, msg = state.join_group(group_name, sender)
    if not success:
        code = ERR_ALREADY_IN_GROUP if "already in" in msg else ERR_GROUP_NOT_FOUND
        logger.warning(f"Join group failed for '{sender}' -> '{group_name}': {msg}")
        send_packet(client_sock, MSG_ERROR, {
            "code": code,
            "message": msg,
        })
        return False

    logger.info(f"User '{sender}' joined group '{group_name}'")
    broadcast_group_list(state)
    return True


def handle_group_msg(
    client_sock: socket.socket,
    payload: Dict[str, Any],
    state: ServerState,
    session: Dict[str, Any],
) -> bool:
    """
    Multicasts group message only to joined members (R11).
    Rejects non-members with ERR_NOT_IN_GROUP.
    """
    group_name = str(payload.get("group", "")).strip()
    text = str(payload.get("text", "")).strip()
    sender = session.get("username", "")

    if not text:
        return False

    member_socks = state.get_group_member_sockets(group_name, sender)
    if not member_socks:
        logger.warning(f"Group message rejected: '{sender}' is not a member of '{group_name}'")
        send_packet(client_sock, MSG_ERROR, {
            "code": ERR_NOT_IN_GROUP,
            "message": f"You must join group '{group_name}' before sending messages",
        })
        return False

    msg_payload = {
        "group": group_name,
        "from": sender,
        "text": text,
    }

    # Multicast to all members in group (including sender)
    for sock in member_socks:
        send_packet(sock, MSG_GROUP, msg_payload)

    logger.info(f"Group message in '{group_name}' from '{sender}' sent to {len(member_socks)} members")
    return True
