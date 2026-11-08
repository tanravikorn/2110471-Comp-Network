"""
Module: server/state.py
Purpose: Thread-Safe In-Memory State Manager for Connected Clients & Chat Groups
Mapped Requirements:
  - R3 (Unique Client Name): Validates and registers unique client usernames.
  - R4 (Connected Client List): Retrieves the list of all currently connected client names.
  - R7 (Private Message Routing): Looks up the target receiver's socket for 1-to-1 delivery.
  - R8 (Create Group): Creates a new group containing only the creator initially.
  - R9 (Group List with Members): Retrieves all existing groups along with their member lists.
  - R10 (Self-Join Group): Adds a requesting client to an existing group.
  - R11 (Group Message Routing): Retrieves sockets of all members belonging to a specific group.
"""

import socket
import threading
from typing import Any, Dict, List, Optional, Set, Tuple


def get_private_room_key(user1: str, user2: str) -> str:
    """Returns canonical room key for 1-on-1 private chat."""
    u1, u2 = sorted([user1.strip(), user2.strip()])
    return f"PRIVATE:{u1}:{u2}"


def get_group_room_key(group_name: str) -> str:
    """Returns canonical room key for group chat."""
    return f"GROUP:{group_name.strip()}"


class ServerState:
    """
    Central thread-safe registry managing:
      - Active client sockets mapped to unique usernames (R3, R4, R7)
      - Chat groups and member sets (R8, R9, R10, R11)
      - In-memory message history per room for AI summarization (B1)
      - Thread synchronization using threading.Lock()
    """

    def __init__(self):
        self.lock = threading.Lock()
        # username -> client socket mapping
        self.clients: Dict[str, socket.socket] = {}
        # group_name -> set of member usernames
        self.groups: Dict[str, Set[str]] = {}
        # room_key -> list of {"timestamp": str, "sender": str, "text": str}
        self.room_history: Dict[str, List[Dict[str, Any]]] = {}
        # Backward-compatible name for room chat history consumers.
        self.history = self.room_history
        # room_keys with an AI summary request currently in flight
        self.summarizing_rooms: Set[str] = set()

    # ==========================================================================
    # 1. Client Registration & Directory (R3, R4, R7)
    # ==========================================================================
    def register_client(self, username: str, sock: socket.socket) -> bool:
        """Attempts to register a client socket under a unique username (R3)."""
        username = username.strip()
        if not username:
            return False

        with self.lock:
            if username in self.clients:
                return False
            self.clients[username] = sock
            return True

    def remove_client(self, username: str) -> None:
        """Removes a client from active directory and group memberships upon disconnect."""
        with self.lock:
            self.clients.pop(username, None)
            for group_name in list(self.groups.keys()):
                self.groups[group_name].discard(username)
                if len(self.groups[group_name]) == 0:
                    del self.groups[group_name]

    def get_client_list(self) -> List[str]:
        """Returns a sorted list of all currently connected usernames (R4)."""
        with self.lock:
            return sorted(list(self.clients.keys()))

    def get_client_socket(self, username: str) -> Optional[socket.socket]:
        """Returns the socket for a given username, or None if offline (R7)."""
        with self.lock:
            return self.clients.get(username)

    def get_all_client_sockets(self) -> List[socket.socket]:
        """Returns a list of all active client sockets for broadcasting (R4)."""
        with self.lock:
            return list(self.clients.values())

    # ==========================================================================
    # 2. Group Management (R8, R9, R10, R11)
    # ==========================================================================
    def create_group(self, group_name: str, creator_username: str) \
        -> Tuple[bool, str]:
        """
        Creates a new group with the creator as its sole initial member (R8).
        """
        group_name = group_name.strip()
        if not group_name:
            return False, "Group name cannot be empty"

        with self.lock:
            if group_name in self.groups:
                return False, f"Group '{group_name}' already exists"
            self.groups[group_name] = {creator_username}
            return True, "Group created successfully"

    def join_group(self, group_name: str, username: str) -> Tuple[bool, str]:
        """
        Adds a user to an existing group upon their explicit request (R10).
        """
        group_name = group_name.strip()
        with self.lock:
            if group_name not in self.groups:
                return False, f"Group '{group_name}' not found"
            if username in self.groups[group_name]:
                return False, f"You are already in group '{group_name}'"
            self.groups[group_name].add(username)
            return True, "Joined group successfully"

    def get_groups_with_members(self) -> Dict[str, List[str]]:
        """
        Returns all existing groups and their member lists (R9).
        e.g. {"StudyRoom": ["Alice", "Bob"]}
        """
        with self.lock:
            return {g: sorted(list(members)) for g, members in self.groups.items()}

    def get_group_member_sockets(
        self, group_name: str, sender_username: str, exclude_sender: bool = False
    ) -> List[socket.socket]:
        """
        Returns active sockets of members in group_name (R11).
        Verifies sender is in group before returning members.
        """
        with self.lock:
            if group_name not in self.groups:
                return []
            members = self.groups[group_name]
            if sender_username not in members:
                return []

            sockets = []
            for member in members:
                if exclude_sender and member == sender_username:
                    continue
                sock = self.clients.get(member)
                if sock:
                    sockets.append(sock)
            return sockets

    # ==========================================================================
    # 3. Chat History & AI Summarization Storage (B1)
    # ==========================================================================
    def record_message(
        self,
        room_key: str,
        sender: str,
        text: str,
        timestamp: str,
        max_history: int = 50,
    ) -> None:
        """
        Stores a chat message record in room_history with a sliding window limit (B1).
        """
        with self.lock:
            if room_key not in self.room_history:
                self.room_history[room_key] = []
            self.room_history[room_key].append({
                "timestamp": timestamp,
                "sender": sender,
                "text": text,
            })
            if len(self.room_history[room_key]) > max_history:
                self.room_history[room_key] = self.room_history[room_key][-max_history:]

    def get_room_history(self, room_key: str) -> List[Dict[str, Any]]:
        """
        Retrieves a shallow copy of the recorded message history for a given room (B1).
        """
        with self.lock:
            return list(self.room_history.get(room_key, []))

    def try_acquire_summary(self, room_key: str) -> bool:
        """Marks room_key as having an in-flight summary; returns False if already running."""
        with self.lock:
            if room_key in self.summarizing_rooms:
                return False
            self.summarizing_rooms.add(room_key)
            return True

    def release_summary(self, room_key: str) -> None:
        """Clears the in-flight summary lock for room_key."""
        with self.lock:
            self.summarizing_rooms.discard(room_key)
