"""
Module: server/handlers/audio.py
Purpose: Action Handler for MSG_VOICE_MSG (Bonus B4 / Special 4)
Mapped Requirements:
  - B4 (Push-to-Talk Voice Message): Relays Base64-encoded .wav audio clips
    over the TCP socket to target recipient (Private 1-on-1) or multicast
    to group members (Group chat).
"""

import logging
import socket
from typing import Any, Dict

from common.protocol import (
    ERR_GROUP_NOT_FOUND,
    ERR_INVALID_PACKET,
    ERR_NOT_IN_GROUP,
    ERR_USER_NOT_FOUND,
    MSG_ERROR,
    MSG_VOICE_MSG,
    ROOM_GROUP,
    ROOM_PRIVATE,
    send_packet,
)
from server.state import ServerState

logger = logging.getLogger("server.handlers.audio")

# Maximum allowed Base64 audio payload size (5 MB ~ 30-60s WAV audio)
MAX_AUDIO_B64_BYTES = 5 * 1024 * 1024


def handle_voice_msg(
    client_sock: socket.socket,
    payload: Dict[str, Any],
    state: ServerState,
    session: Dict[str, Any],
) -> bool:
    """
    Handles relaying Push-to-Talk voice clips in Private and Group chats (B4).

    Validates audio data, checks recipient / group membership, and sends
    the audio payload across TCP sockets with zero external dependencies.
    """
    sender = session.get("username", "")
    if not sender:
        return False

    room_type = str(payload.get("room_type") or ROOM_PRIVATE).strip().upper()
    target = str(payload.get("target") or "").strip()
    audio_b64 = str(payload.get("audio_b64") or "").strip()
    duration_raw = payload.get("duration", 0.0)

    # 1. Validation: target and audio payload must be non-empty
    if not target or not audio_b64:
        logger.warning(f"Voice message rejected from '{sender}': missing target or audio_b64")
        send_packet(client_sock, MSG_ERROR, {
            "code": ERR_INVALID_PACKET,
            "message": "Voice message requires target and audio_b64 payload",
        })
        return False

    # 2. Validation: payload size safety check
    if len(audio_b64) > MAX_AUDIO_B64_BYTES:
        logger.warning(f"Voice message rejected from '{sender}': payload exceeds size limit ({len(audio_b64)} bytes)")
        send_packet(client_sock, MSG_ERROR, {
            "code": ERR_INVALID_PACKET,
            "message": "Voice message payload exceeds maximum size limit (5MB)",
        })
        return False

    try:
        duration = float(duration_raw)
        if duration < 0:
            duration = 0.0
    except (ValueError, TypeError):
        duration = 0.0

    voice_payload = {
        "room_type": room_type,
        "target": target,
        "from": sender,
        "audio_b64": audio_b64,
        "duration": duration,
    }

    # 3. Route: Private 1-on-1 Chat
    if room_type == ROOM_PRIVATE:
        target_sock = state.get_client_socket(target)
        if not target_sock:
            logger.warning(f"Voice message failed: recipient '{target}' is offline")
            send_packet(client_sock, MSG_ERROR, {
                "code": ERR_USER_NOT_FOUND,
                "message": f"User '{target}' is offline",
            })
            return False

        # Deliver to target recipient
        send_packet(target_sock, MSG_VOICE_MSG, voice_payload)

        # Deliver echo copy to sender if sender is not target (allows local playback)
        if target_sock != client_sock:
            send_packet(client_sock, MSG_VOICE_MSG, voice_payload)

        logger.info(f"Voice message ({duration:.1f}s) delivered from '{sender}' to '{target}'")
        return True

    # 4. Route: Group Chat
    elif room_type == ROOM_GROUP:
        groups = state.get_groups_with_members()
        if target not in groups:
            logger.warning(f"Voice message rejected: group '{target}' not found")
            send_packet(client_sock, MSG_ERROR, {
                "code": ERR_GROUP_NOT_FOUND,
                "message": f"Group '{target}' does not exist",
            })
            return False

        if sender not in groups[target]:
            logger.warning(f"Voice message rejected: '{sender}' is not a member of '{target}'")
            send_packet(client_sock, MSG_ERROR, {
                "code": ERR_NOT_IN_GROUP,
                "message": f"You must join group '{target}' before sending voice messages",
            })
            return False

        member_socks = state.get_group_member_sockets(target, sender)
        for sock in member_socks:
            send_packet(sock, MSG_VOICE_MSG, voice_payload)

        logger.info(f"Voice message ({duration:.1f}s) in '{target}' from '{sender}' multicasted to {len(member_socks)} members")
        return True

    # 5. Invalid room_type
    else:
        logger.warning(f"Voice message rejected from '{sender}': unknown room_type '{room_type}'")
        send_packet(client_sock, MSG_ERROR, {
            "code": ERR_INVALID_PACKET,
            "message": f"Unknown room_type '{room_type}'",
        })
        return False
