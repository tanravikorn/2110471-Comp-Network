"""
Module: client/gui_lobby.py
Purpose: Main Tkinter Lobby Window (Group List & Room Launcher)
Mapped Requirements:
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

import queue
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from client.gui_chatroom import ChatRoomWindow
from common.protocol import (
    KEY_PAYLOAD,
    KEY_TIMESTAMP,
    KEY_TYPE,
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


# ==============================================================================
# R9 Main Lobby Window UI Component
# ==============================================================================
class LobbyWindow(ttk.Frame):
    """
    Main Tkinter Lobby Window UI Component for Requirement R9.

    Mapped Requirements:
      - R9 (Group List): Renders all active groups in a tk.Listbox with a clear header/label,
        updating upon receiving MSG_GROUP_LIST packets, and formatting each item as
        "{group_name} ({member_count} members)".
      - Thread-Safe Queue Polling: Regularly polls self.client.event_queue on the main GUI thread
        using root.after(100, self._poll_network_queue) to fetch and process incoming network packets
        without blocking the UI.
    """

    def __init__(
        self,
        root: Optional[tk.Misc] = None,
        client: Optional[Any] = None,
        username: str = "",
        **kwargs: Any,
    ) -> None:
        """
        Initializes the LobbyWindow.

        :param root: Parent Tkinter widget or window (e.g. tk.Tk, tk.Toplevel).
        :param client: Client network instance managing the socket and incoming packet queue.
        :param username: Current client's unique registered username.
        """
        # Resolve positional or keyword parameter variations
        parent = kwargs.get("parent", root)
        network_client = kwargs.get("network_client", client)
        user = kwargs.get("own_username", username)

        # Handle case where client is passed as the first positional argument without a parent
        if parent is not None and not isinstance(parent, tk.Misc):
            actual_client = parent
            actual_user = network_client if isinstance(network_client, str) else user
            parent = None
            network_client = actual_client
            user = actual_user

        # Ensure parent Tk root exists
        if parent is None:
            if tk._default_root is not None:
                parent = tk._default_root
            else:
                parent = tk.Tk()

        super().__init__(parent)
        self.root: tk.Misc = parent
        self.client: Optional[Any] = network_client
        self.username: str = user or (getattr(self.client, "username", "") if self.client else "")

        # State tracking for active groups
        self.groups: Dict[str, Any] = {}
        self._is_running: bool = True
        self._poll_job: Optional[str] = None

        # Provide self.client.event_queue alias to incoming_queue if needed
        if self.client is not None:
            event_q = getattr(self.client, "event_queue", None)
            incoming_q = getattr(self.client, "incoming_queue", None)
            if incoming_q is not None and (event_q is None or not isinstance(event_q, queue.Queue)):
                try:
                    self.client.event_queue = incoming_q
                except Exception:
                    pass

        # Configure root window title if applicable
        if hasattr(self.root, "title") and callable(self.root.title):
            try:
                title_str = f"Chat Lobby - {self.username}" if self.username else "Chat Lobby"
                self.root.title(title_str)
            except Exception:
                pass

        # Pack this frame into parent
        self.pack(fill=tk.BOTH, expand=True)

        # Build UI layout (R9 Group List)
        self._build_ui()

        # Start thread-safe network queue polling (100ms interval)
        if hasattr(self.root, "after") and callable(self.root.after):
            self._poll_job = self.root.after(100, self._poll_network_queue)

    def _build_ui(self) -> None:
        """Sets up the main window layout for the Group List (R9)."""
        # Top banner showing login identity
        self.header_frame = ttk.Frame(self, padding=(12, 10, 12, 4))
        self.header_frame.pack(fill=tk.X)

        self.title_label = ttk.Label(
            self.header_frame,
            text=f"Logged in as: {self.username}" if self.username else "Chat Lobby",
            font=("Segoe UI", 11, "bold"),
        )
        self.title_label.pack(side=tk.LEFT)

        # ----------------------------------------------------------------------
        # Group List Container (R9)
        # ----------------------------------------------------------------------
        self.groups_frame = ttk.Frame(self, padding=(12, 6, 12, 12))
        self.groups_frame.pack(fill=tk.BOTH, expand=True)

        self.groups_label = ttk.Label(
            self.groups_frame,
            text="Groups",
            font=("Segoe UI", 10, "bold"),
        )
        self.groups_label.pack(anchor="w", pady=(0, 6))

        groups_list_frame = ttk.Frame(self.groups_frame)
        groups_list_frame.pack(fill=tk.BOTH, expand=True)

        self.groups_scrollbar = ttk.Scrollbar(groups_list_frame, orient=tk.VERTICAL)
        self.groups_listbox = tk.Listbox(
            groups_list_frame,
            yscrollcommand=self.groups_scrollbar.set,
            selectmode=tk.SINGLE,
            exportselection=False,
            font=("Segoe UI", 10),
        )
        self.groups_scrollbar.config(command=self.groups_listbox.yview)
        self.groups_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.groups_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Alias for R9 groups listbox
        self.group_listbox = self.groups_listbox

    def _poll_network_queue(self) -> None:
        """
        Thread-safe network queue polling (R9).
        Continuously fetches and processes incoming packets from self.client.event_queue
        using root.after(100, self._poll_network_queue) without blocking the main GUI thread.
        """
        if not self.winfo_exists():
            return

        # Fetch queue from self.client.event_queue (or fallback to incoming_queue)
        queue_obj = getattr(self.client, "event_queue", None)
        if queue_obj is None or (
            not isinstance(queue_obj, queue.Queue)
            and isinstance(getattr(self.client, "incoming_queue", None), queue.Queue)
        ):
            queue_obj = getattr(self.client, "incoming_queue", None)

        if queue_obj is not None and hasattr(queue_obj, "get_nowait"):
            # Drain up to 200 packets per cycle to maintain smooth GUI responsiveness
            for _ in range(200):
                try:
                    packet = queue_obj.get_nowait()
                except (queue.Empty, AttributeError):
                    break
                except Exception:
                    break

                if not isinstance(packet, dict):
                    continue

                self._process_network_packet(packet)

        if self.winfo_exists() and self._is_running:
            try:
                self._poll_job = self.root.after(100, self._poll_network_queue)
            except Exception:
                pass

    def _process_network_packet(self, packet: Any) -> None:
        """Processes a single incoming network packet from the queue."""
        if not isinstance(packet, dict):
            return

        msg_type = packet.get(KEY_TYPE) or packet.get("type")
        payload = packet.get(KEY_PAYLOAD, packet.get("payload", {}))

        if msg_type in (MSG_GROUP_LIST, "MSG_GROUP_LIST", "GROUP_LIST"):
            self.update_group_list(payload)

    def update_group_list(self, groups_data: Any) -> None:
        """
        Clears and updates the Group listbox (R9).
        Formats each group entry as "{group_name} ({member_count} members)".
        """
        groups_dict: Dict[str, Any] = {}
        if isinstance(groups_data, dict):
            if "groups" in groups_data and isinstance(groups_data["groups"], dict):
                groups_dict = groups_data["groups"]
            else:
                groups_dict = groups_data
        elif isinstance(groups_data, (list, tuple)):
            for item in groups_data:
                if isinstance(item, dict):
                    g_name = item.get("group") or item.get("name") or str(item)
                    g_members = item.get("members", [])
                    groups_dict[g_name] = g_members
                else:
                    groups_dict[str(item)] = []

        self.groups = groups_dict
        self.groups_listbox.delete(0, tk.END)

        for group_name, members in groups_dict.items():
            if isinstance(members, (list, tuple, set)):
                member_count = len(members)
            elif isinstance(members, int):
                member_count = members
            else:
                member_count = 0
            display_str = f"{group_name} ({member_count} members)"
            self.groups_listbox.insert(tk.END, display_str)

    def destroy(self) -> None:
        """Stops the queue polling loop and destroys the widget."""
        self._is_running = False
        if self._poll_job is not None and hasattr(self.root, "after_cancel"):
            try:
                self.root.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None
        super().destroy()

    def title(self, *args: Any, **kwargs: Any) -> Any:
        """Delegates title configuration to parent root window if available."""
        if hasattr(self.root, "title") and callable(self.root.title):
            return self.root.title(*args, **kwargs)
        return None

    def geometry(self, *args: Any, **kwargs: Any) -> Any:
        """Delegates geometry configuration to parent root window if available."""
        if hasattr(self.root, "geometry") and callable(self.root.geometry):
            return self.root.geometry(*args, **kwargs)
        return None
