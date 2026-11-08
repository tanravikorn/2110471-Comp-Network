"""
Module: client/gui_lobby.py
Purpose: Main Tkinter Lobby Window (Connected Clients List, Group List, & Room Launcher) (R4, R5, R8-R11)
"""

from __future__ import annotations

import queue
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable, Dict, List, Optional

from client.gui_chatroom import ChatRoomWindow
from common.protocol import (
    KEY_PAYLOAD,
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


class ChatRoomManager:
    """Tracks and dispatches messages to dedicated ChatRoomWindow instances (R5, R6)."""

    def __init__(self, parent: tk.Misc, own_username: str, network_client: Any = None) -> None:
        self.parent = parent
        self.own_username = own_username
        self.network_client = network_client
        self.private_rooms: Dict[str, ChatRoomWindow] = {}
        self.group_rooms: Dict[str, ChatRoomWindow] = {}

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
        )
        self.private_rooms[peer_username] = room
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
        )
        if members:
            room.set_participants(members)
        self.group_rooms[group_name] = room
        return room

    def dispatch_private_message(self, sender: str, target: str, text: str, timestamp: str = "") -> None:
        peer = target if sender == self.own_username else sender
        room = self.get_or_create_private_room(peer)
        room.append_message(sender=sender, text=text, timestamp=timestamp)

    def dispatch_group_message(self, group_name: str, sender: str, text: str, timestamp: str = "") -> None:
        room = self.get_or_create_group_room(group_name)
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


class LobbyWindow(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        own_username: str,
        network_client: Any,
    ) -> None:
        super().__init__(parent, padding=12)
        self.own_username = own_username
        self.network_client = network_client
        self.room_manager = ChatRoomManager(parent, own_username, network_client)

        self.clients_list: List[str] = []
        self.groups_data: Dict[str, List[str]] = {}

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(1, weight=1)

        self._build_ui()
        self.after(100, self.poll_incoming_queue)

    def _build_ui(self) -> None:
        header_text = f"Connected Clients ({self.own_username})"
        ttk.Label(self, text=header_text, font=("Helvetica", 10, "bold")).grid(
            row=0, column=0, sticky="w", padx=4, pady=4
        )

        left_frame = ttk.Frame(self)
        left_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        left_frame.rowconfigure(0, weight=1)
        left_frame.columnconfigure(0, weight=1)

        self.clients_listbox = tk.Listbox(left_frame, selectmode=tk.SINGLE)
        self.clients_listbox.grid(row=0, column=0, sticky="nsew")

        scrollbar_clients = ttk.Scrollbar(left_frame, orient="vertical", command=self.clients_listbox.yview)
        scrollbar_clients.grid(row=0, column=1, sticky="ns")
        self.clients_listbox.configure(yscrollcommand=scrollbar_clients.set)

        self.btn_private_chat = ttk.Button(
            self, text="Open Private Chat", command=self._on_open_private_chat_clicked
        )
        self.btn_private_chat.grid(row=2, column=0, sticky="ew", padx=4, pady=4)

        ttk.Label(self, text="Chat Groups", font=("Helvetica", 10, "bold")).grid(
            row=0, column=1, sticky="w", padx=4, pady=4
        )

        right_frame = ttk.Frame(self)
        right_frame.grid(row=1, column=1, sticky="nsew", padx=4, pady=4)
        right_frame.rowconfigure(0, weight=1)
        right_frame.columnconfigure(0, weight=1)

        self.groups_tree = ttk.Treeview(right_frame, columns=("members",), show="tree headings")
        self.groups_tree.heading("#0", text="Group Name")
        self.groups_tree.heading("members", text="Members")
        self.groups_tree.column("#0", width=140)
        self.groups_tree.column("members", width=200)
        self.groups_tree.grid(row=0, column=0, sticky="nsew")

        scrollbar_groups = ttk.Scrollbar(right_frame, orient="vertical", command=self.groups_tree.yview)
        scrollbar_groups.grid(row=0, column=1, sticky="ns")
        self.groups_tree.configure(yscrollcommand=scrollbar_groups.set)

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

    def _on_create_group_clicked(self) -> None:
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
        selected_item = self.groups_tree.selection()
        if not selected_item:
            messagebox.showwarning("Join Group", "Please select a group from the list.")
            return

        item_id = selected_item[0]
        group_name = item_id if item_id in self.groups_data else self.groups_tree.parent(item_id)
        if not group_name:
            return

        if hasattr(self.network_client, "send_join_group"):
            self.network_client.send_join_group(group_name)
        elif hasattr(self.network_client, "send_packet"):
            self.network_client.send_packet(MSG_JOIN_GROUP, {"group": group_name})

    def _on_open_private_chat_clicked(self) -> None:
        selection = self.clients_listbox.curselection()
        if not selection:
            return
        selected_index = selection[0]
        if selected_index < len(self.clients_list):
            target_user = self.clients_list[selected_index]
            if target_user != self.own_username:
                self.room_manager.get_or_create_private_room(target_user)

    def _on_open_group_chat_clicked(self) -> None:
        selected_item = self.groups_tree.selection()
        if not selected_item:
            messagebox.showwarning("Group Chat", "Please select a group first.")
            return

        group_name = selected_item[0] if selected_item[0] in self.groups_data else self.groups_tree.parent(selected_item[0])
        members = self.groups_data.get(group_name, [])

        if self.own_username not in members:
            messagebox.showinfo("Group Chat", f"You must join '{group_name}' before opening the chat window.")
            return

        self.room_manager.get_or_create_group_room(group_name, members)

    def update_connected_clients(self, clients: List[str]) -> None:
        self.clients_list = clients
        self.clients_listbox.delete(0, tk.END)
        for name in self.clients_list:
            display_text = f"{name} (You)" if name == self.own_username else name
            self.clients_listbox.insert(tk.END, display_text)

    def update_groups_display(self, groups_dict: Dict[str, List[str]]) -> None:
        self.groups_data = groups_dict
        for item in self.groups_tree.get_children():
            self.groups_tree.delete(item)

        for group_name, members in groups_dict.items():
            members_str = ", ".join(members)
            self.groups_tree.insert(
                "", tk.END, iid=group_name, text=f"👥 {group_name}", values=(members_str,)
            )

            if group_name in self.room_manager.group_rooms:
                room = self.room_manager.group_rooms[group_name]
                if room.winfo_exists():
                    room.set_participants(members)

    def poll_incoming_queue(self) -> None:
        if not self.winfo_exists():
            return

        try:
            while True:
                msg = self.network_client.incoming_queue.get_nowait()
                msg_type = msg.get(KEY_TYPE)
                payload = msg.get(KEY_PAYLOAD, {})
                ts = msg.get("timestamp", "")

                if msg_type == MSG_CLIENT_LIST:
                    self.update_connected_clients(payload.get("clients", []))
                elif msg_type == MSG_GROUP_LIST:
                    self.update_groups_display(payload.get("groups", {}))
                elif msg_type == MSG_PRIVATE:
                    sender = payload.get("from")
                    target = payload.get("to")
                    text = payload.get("text", "")
                    self.room_manager.dispatch_private_message(sender, target, text, ts)
                elif msg_type == MSG_GROUP:
                    group = payload.get("group")
                    sender = payload.get("from")
                    text = payload.get("text", "")
                    self.room_manager.dispatch_group_message(group, sender, text, ts)
                elif msg_type == MSG_ERROR:
                    err_msg = payload.get("message", "An error occurred.")
                    messagebox.showerror("Server Error", err_msg)

        except queue.Empty:
            pass

        self.after(100, self.poll_incoming_queue)