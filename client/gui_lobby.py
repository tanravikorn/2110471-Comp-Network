"""
Module: client/gui_lobby.py
Purpose: Main Tkinter Lobby Window (Connected Clients List, Group List, & Room Launcher)
Mapped Requirements:
  - R4 (Connected Client List): Displays a live list of all currently connected clients,
    explicitly including the client's own name (e.g., `"Alice (You)"`).
  - R5 (Separate Chat Rooms): Opens and manages dedicated `ChatRoomWindow` (`tk.Toplevel`)
    instances for each Private chat peer and each joined Group chat.
  - R6 (Chat Box & Chat Window): Integrates with `ChatRoomWindow` for message display and sending.
  - R8 (Create Group): Provides UI input/button to create a new chat group (creator is sole initial member).
  - R9 (Group List with Members): Displays all existing chat groups created by any client,
    along with each group's current member list.
  - R10 (Self-Join Group): Provides a "Join Group" button allowing the client to join a selected
    group by themselves (never added automatically by the creator).
"""

from __future__ import annotations

import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable, Dict, List, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from client.gui_chatroom import ChatRoomWindow
from common.protocol import (
    MSG_CLIENT_LIST,
    MSG_CREATE_GROUP,
    MSG_ERROR,
    MSG_GROUP,
    MSG_GROUP_LIST,
    MSG_JOIN_GROUP,
    MSG_PRIVATE,
    ROOM_GROUP,
    ROOM_PRIVATE,
)


# ==============================================================================
# R5 / R6 Chat Room Lifecycle & Dispatch Hooks
# ==============================================================================
class ChatRoomManager:
    """
    Helper manager that tracks and dispatches messages to dedicated ChatRoomWindow instances (R5, R6).
    Maintains a 1-to-1 mapping of open rooms and routes incoming server envelopes seamlessly.
    """

    def __init__(self, parent: tk.Misc, own_username: str, network_client: Any = None) -> None:
        self.parent = parent
        self.own_username = own_username
        self.network_client = network_client
        self.private_rooms: Dict[str, ChatRoomWindow] = {}
        self.group_rooms: Dict[str, ChatRoomWindow] = {}

    def get_or_create_private_room(self, peer_username: str) -> ChatRoomWindow:
        """Retrieves an existing private chat room or opens a dedicated new one (R5)."""
        if peer_username in self.private_rooms:
            room = self.private_rooms[peer_username]
            if room.winfo_exists():
                room.bring_to_front()
                return room

        room = ChatRoomWindow(
            parent=self.parent,
            room_type=ROOM_PRIVATE,
            target_name=peer_username,
            own_username=self.own_username,
            network_client=self.network_client,
            on_close_callback=lambda _rt, target: self.private_rooms.pop(target, None),
        )
        self.private_rooms[peer_username] = room
        return room

    def get_or_create_group_room(self, group_name: str, members: Optional[List[str]] = None) -> ChatRoomWindow:
        """Retrieves an existing group chat room or opens a dedicated new one (R5)."""
        if group_name in self.group_rooms:
            room = self.group_rooms[group_name]
            if room.winfo_exists():
                if members:
                    room.set_participants(members)
                room.bring_to_front()
                return room

        room = ChatRoomWindow(
            parent=self.parent,
            room_type=ROOM_GROUP,
            target_name=group_name,
            own_username=self.own_username,
            network_client=self.network_client,
            on_close_callback=lambda _rt, target: self.group_rooms.pop(target, None),
        )
        if members:
            room.set_participants(members)
        self.group_rooms[group_name] = room
        return room

    def dispatch_private_message(self, sender: str, target: str, text: str, timestamp: str = "") -> None:
        """Routes incoming private message to the appropriate ChatRoomWindow (R5, R6)."""
        peer = target if sender == self.own_username else sender
        room = self.get_or_create_private_room(peer)
        room.append_message(sender=sender, text=text, timestamp=timestamp)

    def dispatch_group_message(self, group_name: str, sender: str, text: str, timestamp: str = "") -> None:
        """Routes incoming group message to the appropriate ChatRoomWindow (R5, R6)."""
        room = self.get_or_create_group_room(group_name)
        room.append_message(sender=sender, text=text, timestamp=timestamp)

    def close_all_rooms(self) -> None:
        """Closes all open chat rooms cleanly upon logout/exit."""
        for room in list(self.private_rooms.values()):
            try:
                room.destroy()
            except Exception:
                pass
        self.private_rooms.clear()

        for room in list(self.group_rooms.values()):
            try:
                room.destroy()
            except Exception:
                pass
        self.group_rooms.clear()
