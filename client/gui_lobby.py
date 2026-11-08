"""
Module: client/gui_lobby.py
Purpose: Main Tkinter Lobby Window (Connected Clients List, Group List, & Room Launcher) (R4, R5, R6, R8, R9, R10, R11, B1, B3, B4)
Mapped Requirements:
  - R4 (Connected Client List): Displays a live list of all currently connected clients,
    explicitly including the client's own name (e.g., `"Alice (You)"`).
  - R5 (Separate Chat Rooms): Opens and manages dedicated `ChatRoomWindow` (`tk.Toplevel`)
    instances for each Private chat peer and each joined Group chat.
  - R6 (Chat Box & Chat Window): Integrates with `ChatRoomWindow` for message display and sending.
  - R8 (Create Group): Provides UI input/button to create a new chat group (creator is sole initial member).
  - R9 (Group List with Members): Displays all existing chat groups created by any client,
    along with each group's current member list and member count.
  - R10 (Self-Join Group): Provides a "Join Group" button allowing the client to join a selected
    group by themselves (never added automatically by the creator).
  - R11 (Group Messaging): Routes group chat messages to open room windows.
  - B1 (AI Summary): Routes `AI_SUMMARY_RES` packets to the corresponding private or group room window.
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
    GET_HISTORY,
    HISTORY_REPLY,
    KEY_PAYLOAD,
    KEY_TIMESTAMP,
    KEY_TYPE,
    MSG_AI_SUMMARY_REQ,
    MSG_AI_SUMMARY_RES,
    MSG_CLIENT_LIST,
    MSG_CREATE_GROUP,
    MSG_ERROR,
    MSG_GROUP,
    MSG_GROUP_LIST,
    MSG_JOIN_GROUP,
    MSG_PRIVATE,
    MSG_TYPING,
    MSG_VOICE_MSG,
    ROOM_GROUP,
    ROOM_PRIVATE,
)


# ==============================================================================
# R5 / R6 Chat Room Lifecycle & Dispatch Hooks
# ==============================================================================
class ChatRoomManager:
    """Tracks and dispatches messages to dedicated ChatRoomWindow instances (R5, R6, B1, B3, B4 Cache)."""

    def __init__(self, parent: tk.Misc, own_username: str, network_client: Any = None) -> None:
        self.parent = parent
        self.own_username = own_username
        self.network_client = network_client
        self.private_rooms: Dict[str, ChatRoomWindow] = {}
        self.group_rooms: Dict[str, ChatRoomWindow] = {}
        # Client-side in-memory cache per (room_type, target) for text & voice clips (B4)
        self.room_cache: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        self.voice_cache = self.room_cache
        self.max_cache_items: int = 50

    def _cache_key(self, room_type: str, target: str) -> Tuple[str, str]:
        return (str(room_type).strip().upper(), str(target).strip())

    def record_text_cache(
        self,
        room_type: str,
        target: str,
        sender: str,
        text: str,
        timestamp: str = "",
    ) -> None:
        """Stores a text message in client-side in-memory room cache."""
        key = self._cache_key(room_type, target)
        bucket = self.room_cache.setdefault(key, [])
        entry = {
            "type": "text",
            "sender": sender,
            "text": text,
            "timestamp": timestamp,
        }
        if bucket and bucket[-1] == entry:
            return
        bucket.append(entry)
        if len(bucket) > self.max_cache_items:
            self.room_cache[key] = bucket[-self.max_cache_items:]

    def record_voice_cache(
        self,
        room_type: str,
        target: str,
        sender: str,
        audio_b64: str,
        duration: float,
        timestamp: str = "",
    ) -> None:
        """Stores a Base64 voice clip in client-side in-memory room cache (B4)."""
        key = self._cache_key(room_type, target)
        bucket = self.room_cache.setdefault(key, [])
        entry = {
            "type": "voice",
            "sender": sender,
            "audio_b64": audio_b64,
            "duration": float(duration),
            "timestamp": timestamp,
        }
        if (
            bucket
            and bucket[-1].get("type") == "voice"
            and bucket[-1].get("sender") == sender
            and bucket[-1].get("audio_b64") == audio_b64
            and bucket[-1].get("timestamp") == timestamp
        ):
            return
        bucket.append(entry)
        if len(bucket) > self.max_cache_items:
            self.room_cache[key] = bucket[-self.max_cache_items:]

    def get_cached_messages(self, room_type: str, target: str) -> List[Dict[str, Any]]:
        """Returns a shallow copy of cached text and voice items for a room."""
        return list(self.room_cache.get(self._cache_key(room_type, target), []))

    def _restore_cached_room_items(self, room: ChatRoomWindow, room_type: str, target: str) -> None:
        """Re-renders cached messages and replayable voice buttons (with autoplay=False) on room reopen."""
        for item in self.get_cached_messages(room_type, target):
            if item.get("type") == "voice":
                room.append_voice_message(
                    sender=str(item.get("sender", "")),
                    audio_b64=str(item.get("audio_b64", "")),
                    duration=float(item.get("duration", 0.0)),
                    timestamp=str(item.get("timestamp", "")),
                    autoplay=False,
                )
            else:
                room.append_message(
                    sender=str(item.get("sender", "")),
                    text=str(item.get("text", "")),
                    timestamp=str(item.get("timestamp", "")),
                )

    def get_or_create_private_room(self, peer_username: str) -> ChatRoomWindow:
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
            on_voice_sent_callback=self.record_voice_cache,
        )
        self.private_rooms[peer_username] = room
        self._restore_cached_room_items(room, ROOM_PRIVATE, peer_username)
        return room

    def get_or_create_group_room(self, group_name: str, members: Optional[List[str]] = None) -> ChatRoomWindow:
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
            on_voice_sent_callback=self.record_voice_cache,
        )
        if members:
            room.set_participants(members)
        self.group_rooms[group_name] = room
        self._restore_cached_room_items(room, ROOM_GROUP, group_name)
        return room

    def _request_history(self, room_type: str, target: str) -> None:
        if hasattr(self.network_client, "send_get_history"):
            self.network_client.send_get_history(room_type, target)
        elif hasattr(self.network_client, "send_packet"):
            self.network_client.send_packet(GET_HISTORY, {
                "room_type": room_type,
                "target": target,
            })

    def dispatch_history(self, room_type: str, target: str, history: Any) -> None:
        if not isinstance(history, list):
            return
        if room_type == ROOM_PRIVATE:
            room = self.private_rooms.get(target)
        else:
            room = self.group_rooms.get(target)
        if room and room.winfo_exists():
            room.render_history(history)

    def dispatch_private_message(self, sender: str, target: str, text: str, timestamp: str = "") -> None:
        peer = target if sender == self.own_username else sender
        room = self.get_or_create_private_room(peer)
        self.record_text_cache(ROOM_PRIVATE, peer, sender, text, timestamp)
        room.append_message(sender=sender, text=text, timestamp=timestamp)

    def dispatch_group_message(self, group_name: str, sender: str, text: str, timestamp: str = "") -> None:
        room = self.get_or_create_group_room(group_name)
        self.record_text_cache(ROOM_GROUP, group_name, sender, text, timestamp)
        room.append_message(sender=sender, text=text, timestamp=timestamp)

    def close_all_rooms(self) -> None:
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

    def dispatch_typing(self, room_type: str, target: str, sender: str, is_typing: bool) -> None:
        """Dispatches real-time typing status updates to the matching room window (B3)."""
        peer = sender if room_type == ROOM_PRIVATE else target
        room = self.private_rooms.get(peer) if room_type == ROOM_PRIVATE else self.group_rooms.get(target)
        if room and room.winfo_exists():
            room.set_typing_status(sender, is_typing)

    def dispatch_voice_message(self, room_type: str, target: str, sender: str, audio_b64: str, duration: float, timestamp: str = "") -> None:
        """Routes incoming Base64 voice messages to the matching chat room window and stores in client cache (B4)."""
        effective_sender = sender if sender else target
        peer = target if effective_sender == self.own_username else effective_sender
        room_target = peer if room_type == ROOM_PRIVATE else target
        room = self.get_or_create_private_room(peer) if room_type == ROOM_PRIVATE else self.get_or_create_group_room(target)
        self.record_voice_cache(room_type, room_target, effective_sender, audio_b64, duration, timestamp)
        room.append_voice_message(sender=effective_sender, audio_b64=audio_b64, duration=duration, timestamp=timestamp)

    def dispatch_ai_summary(
        self,
        room_type: str,
        target: str,
        summary: str,
        requested_by: str = "",
        timestamp: str = "",
    ) -> None:
        """Routes incoming AI conversation summaries to the matching chat room window (B1)."""
        if room_type == ROOM_GROUP:
            room = self.get_or_create_group_room(target)
        else:
            peer = target if (not requested_by or requested_by == self.own_username) else requested_by
            room = self.get_or_create_private_room(peer)
        room.display_ai_summary(summary=summary, requested_by=requested_by, timestamp=timestamp)

    def clear_all_ai_summary_loading(self) -> None:
        """Clears pending AI summary loading state across all open rooms on server error (B1)."""
        for room in list(self.private_rooms.values()) + list(self.group_rooms.values()):
            try:
                if room and room.winfo_exists() and hasattr(room, "clear_ai_summary_loading"):
                    room.clear_ai_summary_loading()
            except Exception:
                pass


# ==============================================================================
# R4, R5, R8, R9, R10, R11 Main Lobby Window UI Component
# ==============================================================================
class LobbyWindow(ttk.Frame):
    """
    Main Tkinter Lobby Window UI Component.

    Mapped Requirements:
      - R4 (Online Users List): Renders a list of all currently connected clients in a tk.Listbox
        with a clear header/label, updating upon receiving MSG_CLIENT_LIST packets, and explicitly
        formatting the client's own username as "{username} (You)".
      - R5 (Separate Chat Rooms): Controls to open dedicated private chat and group chat rooms.
      - R8 (Create Group): Provides UI input/button to create a new chat group.
      - R9 (Group List): Renders all active groups with member lists in Treeview and Listbox,
        updating upon receiving MSG_GROUP_LIST packets, and formatting items as
        "{group_name} ({member_count} members)".
      - R10 (Self-Join Group): Button to explicitly join a selected chat group.
      - R11 (Group Messaging): Automatically routes group messages to open room windows.
      - Thread-Safe Queue Polling: Regularly polls incoming packet queue on the main GUI thread
        using after(100) to fetch and process incoming network packets without blocking the UI.
    """

    def __init__(
        self,
        parent: Optional[tk.Misc] = None,
        own_username: str = "",
        network_client: Optional[Any] = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """
        Initializes the LobbyWindow.

        Accommodates both positional and keyword argument patterns:
          LobbyWindow(parent, own_username, network_client)
          LobbyWindow(root=parent, username=username, client=network_client)
        """
        # Resolve argument variations flexibly
        actual_parent = kwargs.get("root", kwargs.get("parent", parent))
        actual_username = kwargs.get("username", kwargs.get("own_username", own_username))
        actual_client = kwargs.get("client", kwargs.get("network_client", network_client))

        # Handle case where client is passed as the first positional argument without a parent
        if actual_parent is not None and not isinstance(actual_parent, tk.Misc):
            if actual_client is None:
                actual_client = actual_parent
                actual_parent = None

        # Ensure a Tk parent exists
        if actual_parent is None:
            if tk._default_root is not None:
                actual_parent = tk._default_root
            else:
                actual_parent = tk.Tk()

        super().__init__(actual_parent, padding=12)
        self.root: tk.Misc = actual_parent
        self.parent: tk.Misc = actual_parent
        self.own_username: str = actual_username or (getattr(actual_client, "username", "") if actual_client else "")
        self.username: str = self.own_username
        self.network_client: Optional[Any] = actual_client
        self.client: Optional[Any] = actual_client

        # Chat Room Manager (R5, R6)
        self.room_manager = ChatRoomManager(actual_parent, self.own_username, self.network_client)

        # State tracking for online users (R4) and groups (R9)
        self.clients_list: List[str] = []
        self.online_users: List[str] = self.clients_list
        self.groups_data: Dict[str, List[str]] = {}
        self.groups: Dict[str, Any] = self.groups_data

        self._is_running: bool = True
        self._poll_job: Optional[str] = None

        # Provide self.network_client.event_queue alias to incoming_queue if needed
        if self.network_client is not None:
            event_q = getattr(self.network_client, "event_queue", None)
            incoming_q = getattr(self.network_client, "incoming_queue", None)
            if incoming_q is not None and (event_q is None or not isinstance(event_q, queue.Queue)):
                try:
                    self.network_client.event_queue = incoming_q
                except Exception:
                    pass

        # Configure root window title if applicable
        if hasattr(self.root, "title") and callable(self.root.title):
            try:
                title_str = f"Network Chat — Logged in as {self.own_username}" if self.own_username else "Chat Lobby"
                self.root.title(title_str)
            except Exception:
                pass

        # Build UI layout (R4 Left, R9 Right, Controls below)
        self._build_ui()

        # Start thread-safe incoming queue polling (100ms interval)
        if hasattr(self, "after") and callable(self.after):
            self._poll_job = self.after(100, self.poll_incoming_queue)

    def _build_ui(self) -> None:
        """Sets up the 2-column layout (Left: Users R4/R5, Right: Groups R8/R9/R10)."""
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(1, weight=1)

        # ----------------------------------------------------------------------
        # Left Pane: Online Users List (R4) & Private Chat Launcher (R5)
        # ----------------------------------------------------------------------
        header_text = f"Connected Clients ({self.own_username})" if self.own_username else "Connected Clients"
        self.clients_label = ttk.Label(self, text=header_text, font=("Helvetica", 10, "bold"))
        self.clients_label.grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.users_label = self.clients_label

        left_frame = ttk.Frame(self)
        left_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        left_frame.rowconfigure(0, weight=1)
        left_frame.columnconfigure(0, weight=1)
        self.users_frame = left_frame

        self.clients_listbox = tk.Listbox(left_frame, selectmode=tk.SINGLE, font=("Segoe UI", 10))
        self.clients_listbox.grid(row=0, column=0, sticky="nsew")
        self.users_listbox = self.clients_listbox
        self.client_listbox = self.clients_listbox

        scrollbar_clients = ttk.Scrollbar(left_frame, orient="vertical", command=self.clients_listbox.yview)
        scrollbar_clients.grid(row=0, column=1, sticky="ns")
        self.clients_listbox.configure(yscrollcommand=scrollbar_clients.set)

        self.btn_private_chat = ttk.Button(
            self, text="Open Private Chat", command=self._on_open_private_chat_clicked
        )
        self.btn_private_chat.grid(row=2, column=0, sticky="ew", padx=4, pady=4)

        # ----------------------------------------------------------------------
        # Right Pane: Chat Groups (R9), Creation (R8), and Joining (R10)
        # ----------------------------------------------------------------------
        self.groups_label = ttk.Label(self, text="Chat Groups", font=("Helvetica", 10, "bold"))
        self.groups_label.grid(row=0, column=1, sticky="w", padx=4, pady=4)

        right_frame = ttk.Frame(self)
        right_frame.grid(row=1, column=1, sticky="nsew", padx=4, pady=4)
        right_frame.rowconfigure(0, weight=1)
        right_frame.columnconfigure(0, weight=1)
        self.groups_frame = right_frame

        # Treeview display for group name and members list (R9)
        self.groups_tree = ttk.Treeview(right_frame, columns=("members",), show="tree headings")
        self.groups_tree.heading("#0", text="Group Name")
        self.groups_tree.heading("members", text="Members")
        self.groups_tree.column("#0", width=160)
        self.groups_tree.column("members", width=220)
        self.groups_tree.grid(row=0, column=0, sticky="nsew")
        self.group_tree = self.groups_tree

        scrollbar_groups = ttk.Scrollbar(right_frame, orient="vertical", command=self.groups_tree.yview)
        scrollbar_groups.grid(row=0, column=1, sticky="ns")
        self.groups_tree.configure(yscrollcommand=scrollbar_groups.set)

        # Underlying Listbox for R9 listbox API compatibility
        self.groups_listbox = tk.Listbox(right_frame, selectmode=tk.SINGLE, font=("Segoe UI", 10))
        self.group_listbox = self.groups_listbox

        # Group Actions Bar (R8 Create, R10 Join, R5 Open Group Chat)
        actions_frame = ttk.Frame(self)
        actions_frame.grid(row=2, column=1, sticky="ew", padx=4, pady=4)

        create_box = ttk.Frame(actions_frame)
        create_box.pack(fill="x", pady=(0, 4))

        self.group_name_entry = ttk.Entry(create_box)
        self.group_name_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.group_name_entry.bind("<Return>", lambda _e: self._on_create_group_clicked())

        self.btn_create_group = ttk.Button(
            create_box, text="Create Group", command=self._on_create_group_clicked
        )
        self.btn_create_group.pack(side="right")

        btn_box = ttk.Frame(actions_frame)
        btn_box.pack(fill="x")

        self.btn_join_group = ttk.Button(
            btn_box, text="Join Selected Group", command=self._on_join_group_clicked
        )
        self.btn_join_group.pack(side="left", fill="x", expand=True, padx=(0, 2))

        self.btn_open_group = ttk.Button(
            btn_box, text="Open Group Chat", command=self._on_open_group_chat_clicked
        )
        self.btn_open_group.pack(side="right", fill="x", expand=True, padx=(2, 0))

    def _get_selected_group(self) -> Optional[str]:
        """Retrieves currently selected group name from groups_tree or groups_listbox."""
        if hasattr(self, "groups_tree"):
            selected_item = self.groups_tree.selection()
            if selected_item:
                item_id = selected_item[0]
                group_name = item_id if item_id in self.groups_data else self.groups_tree.parent(item_id)
                if group_name:
                    return group_name

        if hasattr(self, "groups_listbox"):
            sel = self.groups_listbox.curselection()
            if sel:
                item_text = self.groups_listbox.get(sel[0])
                group_name = item_text.split(" (")[0]
                if group_name:
                    return group_name

        return None

    def _on_create_group_clicked(self) -> None:
        """Transmits CREATE_GROUP packet for the entered group name (R8)."""
        group_name = self.group_name_entry.get().strip()
        if not group_name:
            messagebox.showwarning("Create Group", "Please enter a group name.")
            return

        if hasattr(self.network_client, "send_create_group"):
            self.network_client.send_create_group(group_name)
        elif hasattr(self.network_client, "send_packet"):
            self.network_client.send_packet(MSG_CREATE_GROUP, {"group": group_name})

        self.group_name_entry.delete(0, tk.END)

    def _on_join_group_clicked(self) -> None:
        """Transmits JOIN_GROUP packet for the selected group (R10)."""
        group_name = self._get_selected_group()
        if not group_name:
            messagebox.showwarning("Join Group", "Please select a group from the list.")
            return

        if hasattr(self.network_client, "send_join_group"):
            self.network_client.send_join_group(group_name)
        elif hasattr(self.network_client, "send_packet"):
            self.network_client.send_packet(MSG_JOIN_GROUP, {"group": group_name})

    def _on_open_private_chat_clicked(self) -> None:
        """Opens dedicated private chat room window with selected user (R5)."""
        selection = self.clients_listbox.curselection()
        if not selection:
            return
        selected_index = selection[0]
        if selected_index < len(self.clients_list):
            target_user = self.clients_list[selected_index]
            if target_user != self.own_username:
                self.room_manager.get_or_create_private_room(target_user)

    def _on_open_group_chat_clicked(self) -> None:
        """Opens dedicated group chat room window for selected joined group (R5)."""
        group_name = self._get_selected_group()
        if not group_name:
            messagebox.showwarning("Group Chat", "Please select a group first.")
            return

        members = self.groups_data.get(group_name, [])
        if self.own_username not in members:
            messagebox.showinfo("Group Chat", f"You must join '{group_name}' before opening the chat window.")
            return

        self.room_manager.get_or_create_group_room(group_name, members)

    def update_connected_clients(self, clients: Any) -> None:
        """
        Clears and updates the Online Users listbox (R4).
        Formats own username explicitly as "{username} (You)".
        """
        raw_list: List[Any] = []
        if isinstance(clients, dict):
            raw_list = clients.get("clients", clients.get("users", []))
        elif isinstance(clients, (list, tuple, set)):
            raw_list = list(clients)

        client_names = [str(c) for c in raw_list]
        self.clients_list = client_names
        self.online_users = client_names

        self.clients_listbox.delete(0, tk.END)
        for name in client_names:
            display_text = f"{name} (You)" if name == self.own_username else name
            self.clients_listbox.insert(tk.END, display_text)

    # Alias for R4 compatibility
    update_client_list = update_connected_clients

    def update_groups_display(self, groups_dict: Any) -> None:
        """
        Clears and updates the Group display in groups_tree and groups_listbox (R9).
        Formats each group entry as "{group_name} ({member_count} members)".
        """
        if isinstance(groups_dict, dict) and "groups" in groups_dict and isinstance(groups_dict["groups"], dict):
            groups_dict = groups_dict["groups"]

        if not isinstance(groups_dict, dict):
            temp: Dict[str, List[str]] = {}
            if isinstance(groups_dict, (list, tuple)):
                for item in groups_dict:
                    if isinstance(item, dict):
                        g_name = item.get("group") or item.get("name") or str(item)
                        g_members = item.get("members", [])
                        temp[g_name] = list(g_members) if isinstance(g_members, (list, tuple, set)) else []
                    else:
                        temp[str(item)] = []
            groups_dict = temp

        self.groups_data = groups_dict
        self.groups = groups_dict

        # Update Treeview (origin/main)
        if hasattr(self, "groups_tree"):
            for item in self.groups_tree.get_children():
                self.groups_tree.delete(item)

            for group_name, members in groups_dict.items():
                m_list = list(members) if isinstance(members, (list, tuple, set)) else []
                members_str = ", ".join(m_list)
                self.groups_tree.insert(
                    "", tk.END, iid=group_name, text=f"👥 {group_name}", values=(members_str,)
                )

                if hasattr(self, "room_manager") and group_name in self.room_manager.group_rooms:
                    room = self.room_manager.group_rooms[group_name]
                    if room.winfo_exists():
                        room.set_participants(m_list)

        # Update Listbox (R9 "{group_name} ({member_count} members)")
        if hasattr(self, "groups_listbox"):
            self.groups_listbox.delete(0, tk.END)
            for group_name, members in groups_dict.items():
                m_count = len(members) if isinstance(members, (list, tuple, set)) else (int(members) if isinstance(members, int) else 0)
                display_str = f"{group_name} ({m_count} members)"
                self.groups_listbox.insert(tk.END, display_str)

    # Alias for R9 compatibility
    update_group_list = update_groups_display

    def poll_incoming_queue(self) -> None:
        """
        Thread-safe queue polling running on Tkinter's event loop (R4, R9, R11).
        Drains up to 200 packets per 100ms cycle without blocking the GUI thread.
        """
        if not self.winfo_exists() or not self._is_running:
            return

        queue_obj = getattr(self.network_client, "event_queue", None)
        if queue_obj is None or (
            not isinstance(queue_obj, queue.Queue)
            and isinstance(getattr(self.network_client, "incoming_queue", None), queue.Queue)
        ):
            queue_obj = getattr(self.network_client, "incoming_queue", None)

        if queue_obj is not None and hasattr(queue_obj, "get_nowait"):
            for _ in range(200):
                try:
                    msg = queue_obj.get_nowait()
                except (queue.Empty, AttributeError):
                    break
                except Exception:
                    break

                if not isinstance(msg, dict):
                    continue

                self._process_network_packet(msg)

        if self.winfo_exists() and self._is_running:
            try:
                self._poll_job = self.after(100, self.poll_incoming_queue)
            except Exception:
                pass

    # Alias for R9 requirement
    _poll_network_queue = poll_incoming_queue

    def _process_network_packet(self, msg: Dict[str, Any]) -> None:
        """Routes an incoming packet from the network queue to the corresponding handler."""
        msg_type = msg.get(KEY_TYPE) or msg.get("type")
        payload = msg.get(KEY_PAYLOAD, msg.get("payload", {}))
        ts = msg.get(KEY_TIMESTAMP, msg.get("timestamp", ""))

        if msg_type in (MSG_CLIENT_LIST, "MSG_CLIENT_LIST", "CLIENT_LIST"):
            clients = payload.get("clients", payload.get("users", [])) if isinstance(payload, dict) else payload
            self.update_connected_clients(clients)
        elif msg_type in (MSG_GROUP_LIST, "MSG_GROUP_LIST", "GROUP_LIST"):
            groups = payload.get("groups", payload) if isinstance(payload, dict) else payload
            self.update_groups_display(groups)
        elif msg_type in (MSG_PRIVATE, "MSG_PRIVATE", "PRIVATE_MSG"):
            sender = payload.get("from")
            target = payload.get("to")
            text = payload.get("text", "")
            if sender and target and hasattr(self, "room_manager"):
                self.room_manager.dispatch_private_message(sender, target, text, ts)
        elif msg_type in (MSG_GROUP, "MSG_GROUP", "GROUP_MSG"):
            group = payload.get("group")
            sender = payload.get("from")
            text = payload.get("text", "")
            if group and sender and hasattr(self, "room_manager"):
                self.room_manager.dispatch_group_message(group, sender, text, ts)
        elif msg_type in (GET_HISTORY, HISTORY_REPLY, "GET_HISTORY", "HISTORY_REPLY"):
            room_type = str(payload.get("room_type", "")).upper()
            target = str(payload.get("target", "")).strip()
            history = payload.get("history", [])
            if room_type in (ROOM_PRIVATE, ROOM_GROUP) and target and hasattr(self, "room_manager"):
                self.room_manager.dispatch_history(room_type, target, history)
        elif msg_type in (MSG_ERROR, "MSG_ERROR", "ERROR"):
            if hasattr(self, "room_manager") and hasattr(self.room_manager, "clear_all_ai_summary_loading"):
                self.room_manager.clear_all_ai_summary_loading()
            err_msg = payload.get("message", "An error occurred.")
            try:
                messagebox.showerror("Server Error", err_msg)
            except Exception:
                pass
        elif msg_type in (MSG_TYPING, "MSG_TYPING", "TYPING"):
            room_type = str(payload.get("room_type", "")).upper()
            target = str(payload.get("target", "")).strip()
            sender = str(payload.get("from") or payload.get("sender") or "").strip()
            is_typing = payload.get("is_typing", False)
            if hasattr(self, "room_manager"):
                self.room_manager.dispatch_typing(room_type, target, sender, is_typing)
        elif msg_type in (MSG_VOICE_MSG, "MSG_VOICE_MSG", "VOICE_MSG"):
            room_type = str(payload.get("room_type", "")).upper()
            target = str(payload.get("target") or payload.get("to") or payload.get("group") or "").strip()
            sender = str(payload.get("from") or payload.get("sender") or payload.get("from_user") or "").strip()
            audio_b64 = str(payload.get("audio_b64", "")).strip()
            duration = float(payload.get("duration", 0.0))

            # Ignore server echo back to sender (already rendered locally)
            if sender and sender == self.own_username:
                return

            if hasattr(self, "room_manager"):
                self.room_manager.dispatch_voice_message(room_type, target, sender, audio_b64, duration, ts)
        elif msg_type in (MSG_AI_SUMMARY_RES, "MSG_AI_SUMMARY_RES", "AI_SUMMARY_RES"):
            room_type = str(payload.get("room_type", "")).upper()
            target = str(payload.get("target", "")).strip()
            requested_by = str(payload.get("requested_by", "")).strip()
            summary = str(payload.get("summary", "")).strip()
            if room_type in (ROOM_PRIVATE, ROOM_GROUP) and target and summary and hasattr(self, "room_manager"):
                self.room_manager.dispatch_ai_summary(room_type, target, summary, requested_by, ts)

    def destroy(self) -> None:
        """Stops the queue polling loop and cleans up open chat rooms and widgets."""
        self._is_running = False
        if self._poll_job is not None and hasattr(self, "after_cancel"):
            try:
                self.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None
        if hasattr(self, "room_manager") and hasattr(self.room_manager, "close_all_rooms"):
            try:
                self.room_manager.close_all_rooms()
            except Exception:
                pass
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
