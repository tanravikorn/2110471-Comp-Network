"""
Module: server/handlers/historyhandle.py
Purpose: Retrieve thread-safe chat history for a private or group room.
"""

import logging
import socket
from typing import Any, Dict, List

from common.protocol import (
    ERR_GROUP_NOT_FOUND,
    ERR_INVALID_PACKET,
    ERR_NOT_IN_GROUP,
    GET_HISTORY,
    MSG_ERROR,
    ROOM_GROUP,
    ROOM_PRIVATE,
    send_packet,
)
from server.state import ServerState, get_group_room_key, get_private_room_key

logger = logging.getLogger("server.handlers.historyhandle")


def handle_get_history(
    client_sock: socket.socket,
    payload: Dict[str, Any],
    state: ServerState,
    session: Dict[str, Any],
) -> bool:
    """
    Returns recorded chat history for the requested private room or group room.
    """
    sender = str(session.get("username", "")).strip()
    room_type = str(payload.get("room_type", "")).strip().upper()
    target = str(payload.get("target", "")).strip()

    if not target or room_type not in (ROOM_PRIVATE, ROOM_GROUP):
        send_packet(client_sock, MSG_ERROR, {
            "code": ERR_INVALID_PACKET,
            "message": "History requires valid 'room_type' and 'target'",
        })
        return False

    if room_type == ROOM_GROUP:
        groups = state.get_groups_with_members()
        if target not in groups:
            send_packet(client_sock, MSG_ERROR, {
                "code": ERR_GROUP_NOT_FOUND,
                "message": f"Group '{target}' does not exist",
            })
            return False
        if sender not in groups[target]:
            send_packet(client_sock, MSG_ERROR, {
                "code": ERR_NOT_IN_GROUP,
                "message": f"You must be a member of group '{target}' to view its history",
            })
            return False
        room_key = get_group_room_key(target)
    else:
        room_key = get_private_room_key(sender, target)

    history: List[Dict[str, Any]] = []
    getter = getattr(state, "get_room_history", None)
    if callable(getter):
        history = getter(room_key)
    else:
        existing_history = getattr(state, "history", {})
        if isinstance(existing_history, dict):
            state_lock = getattr(state, "lock", None)
            if state_lock is not None:
                with state_lock:
                    history = list(existing_history.get(room_key, []))
            else:
                history = list(existing_history.get(room_key, []))
        elif isinstance(existing_history, list):
            history = list(existing_history)

    response_payload = {
        "room_type": room_type,
        "target": target,
        "history": history,
    }
    return send_packet(client_sock, GET_HISTORY, response_payload)


handle_history = handle_get_history
