"""
Module: server/handlers/ai_summary.py
Purpose: Action Handler for MSG_AI_SUMMARY_REQ (Bonus B1)
Mapped Requirements:
  - B1 (AI Summary Bonus): Validates chat room membership, generates summary via
    server/ai_service.py in a background thread, and broadcasts MSG_AI_SUMMARY_RES
    to all active participants in that room.
"""

import logging
import socket
import threading
from typing import Any, Dict

from common.protocol import (
    ERR_AI_UNAVAILABLE,
    ERR_GROUP_NOT_FOUND,
    ERR_INVALID_PACKET,
    ERR_NOT_IN_GROUP,
    MSG_AI_SUMMARY_RES,
    MSG_ERROR,
    ROOM_GROUP,
    ROOM_PRIVATE,
    send_packet,
)
from server.ai_service import generate_chat_summary
from server.state import ServerState, get_group_room_key, get_private_room_key

logger = logging.getLogger("server.handlers.ai_summary")


def handle_ai_summary(
    client_sock: socket.socket,
    payload: Dict[str, Any],
    state: ServerState,
    session: Dict[str, Any],
) -> bool:
    """
    Handles AI conversation summary request (B1).
    Validates room permissions, launches summarization asynchronously,
    and broadcasts AI_SUMMARY_RES to participants.
    """
    sender = session.get("username", "")
    room_type = str(payload.get("room_type", "")).upper()
    target = str(payload.get("target", "")).strip()

    if not target or room_type not in (ROOM_PRIVATE, ROOM_GROUP):
        logger.warning(f"AI Summary request rejected from '{sender}': Invalid payload ({payload})")
        send_packet(client_sock, MSG_ERROR, {
            "code": ERR_INVALID_PACKET,
            "message": "AI summary requires valid 'room_type' (PRIVATE or GROUP) and 'target'",
        })
        return False

    # 1. Permission checks & room key resolution
    if room_type == ROOM_GROUP:
        groups = state.get_groups_with_members()
        if target not in groups:
            logger.warning(f"AI Summary rejected: group '{target}' not found")
            send_packet(client_sock, MSG_ERROR, {
                "code": ERR_GROUP_NOT_FOUND,
                "message": f"Group '{target}' does not exist",
            })
            return False
        if sender not in groups[target]:
            logger.warning(f"AI Summary rejected: '{sender}' is not a member of group '{target}'")
            send_packet(client_sock, MSG_ERROR, {
                "code": ERR_NOT_IN_GROUP,
                "message": f"You must be a member of group '{target}' to request an AI summary",
            })
            return False
        room_key = get_group_room_key(target)
    else:
        room_key = get_private_room_key(sender, target)

    # 2. Fetch recorded room history
    history = state.get_room_history(room_key)
    if not history:
        logger.info(f"AI Summary requested for empty room '{room_key}' by '{sender}'")
        send_packet(client_sock, MSG_ERROR, {
            "code": ERR_AI_UNAVAILABLE,
            "message": "No chat messages in this room to summarize yet.",
        })
        return False

    # 3. Guard against duplicate concurrent requests for the same room
    if not state.try_acquire_summary(room_key):
        logger.info(f"AI Summary already in progress for '{room_key}'")
        return False

    # 4. Asynchronous execution so network loop is never blocked
    def _async_worker():
        try:
            success, summary_text = generate_chat_summary(target, history)
            if not success:
                send_packet(client_sock, MSG_ERROR, {
                    "code": ERR_AI_UNAVAILABLE,
                    "message": summary_text,
                })
                return

            res_payload = {
                "room_type": room_type,
                "target": target,
                "requested_by": sender,
                "summary": summary_text,
            }

            # Resolve live sockets right before sending
            if room_type == ROOM_GROUP:
                for sock in state.get_group_member_sockets(target, sender):
                    send_packet(sock, MSG_AI_SUMMARY_RES, res_payload)
            else:
                send_packet(client_sock, MSG_AI_SUMMARY_RES, res_payload)
                peer_sock = state.get_client_socket(target)
                if peer_sock and peer_sock != client_sock:
                    send_packet(peer_sock, MSG_AI_SUMMARY_RES, res_payload)

            logger.info(f"AI Summary for '{room_key}' dispatched")
        except Exception as exc:
            logger.error(f"Error in async AI summary worker: {exc}", exc_info=True)
            send_packet(client_sock, MSG_ERROR, {
                "code": ERR_AI_UNAVAILABLE,
                "message": f"AI service failed: {exc}",
            })
        finally:
            state.release_summary(room_key)

    threading.Thread(target=_async_worker, daemon=True).start()
    return True
