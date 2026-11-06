"""
Module: server/state.py
Purpose: Thread-Safe In-Memory State Manager for Connected Clients, Chat Groups, & Room History
Mapped Requirements:
  - R3 (Unique Client Name): Validates and registers unique client usernames.
  - R4 (Connected Client List): Retrieves the list of all currently connected client names.
  - R7 (Private Message Routing): Looks up the target receiver's socket for 1-to-1 delivery.
"""

import socket
import threading
from typing import Dict, List, Optional, Set, Tuple


class ServerState:
    """
    Central thread-safe registry managing:
      - Active client sockets mapped to unique usernames (R3, R4, R7)
      - Thread synchronization using threading.Lock()
    """

    def __init__(self):
        self.lock = threading.Lock()
        # username -> client socket mapping
        self.clients: Dict[str, socket.socket] = {}
        # group_name -> set of member usernames (to be used in R8-R11)
        self.groups: Dict[str, Set[str]] = {}

    # ==========================================================================
    # 1. Client Registration & Directory (R3, R4)
    # ==========================================================================
    def register_client(self, username: str, sock: socket.socket) -> bool:
        """
        Attempts to register a client socket under a unique username (R3).
        Returns True if successful, False if the username is empty or already in use.
        """
        username = username.strip()
        if not username:
            return False

        with self.lock:
            if username in self.clients:
                return False
            self.clients[username] = sock
            return True

    def remove_client(self, username: str) -> None:
        """
        Removes a client from active directory upon disconnection.
        """
        with self.lock:
            self.clients.pop(username, None)
            for member_set in self.groups.values():
                member_set.discard(username)

    def get_client_list(self) -> List[str]:
        """
        Returns a sorted list of all currently connected usernames (R4).
        """
        with self.lock:
            return sorted(list(self.clients.keys()))

    def get_client_socket(self, username: str) -> Optional[socket.socket]:
        """
        Returns the socket for a given username, or None if offline (R7).
        """
        with self.lock:
            return self.clients.get(username)

    def get_all_client_sockets(self) -> List[socket.socket]:
        """
        Returns a list of all active client sockets for broadcasting (R4).
        """
        with self.lock:
            return list(self.clients.values())
