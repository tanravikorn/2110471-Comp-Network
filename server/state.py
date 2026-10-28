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

# ==============================================================================
# TODO 1: Define `ServerState` Class with Thread Synchronization
# ==============================================================================
# - Initialize `self.lock = threading.Lock()` to protect concurrent access from multiple client threads.
# - Initialize `self.clients: dict[str, socket.socket] = {}` mapping `username -> client_socket`.
# - Initialize `self.groups: dict[str, set[str]] = {}` mapping `group_name -> set of member usernames`.
#   (Or use a list/ordered structure if preserving member join order is desired.)

# ==============================================================================
# TODO 2: Implement Client Registration & Removal Methods (R3, R4)
# ==============================================================================
# - `register_client(username: str, sock: socket.socket) -> bool`:
#     Acquire `self.lock`. Check if `username` is non-empty and not already in `self.clients`.
#     If unique, store `self.clients[username] = sock` and return `True`; otherwise return `False` (R3).
#
# - `remove_client(username: str) -> None`:
#     Acquire `self.lock`. Remove `username` from `self.clients`.
#     (Decide whether disconnected users stay listed or are removed from `self.groups` member sets.)
#
# - `get_client_list() -> list[str]`:
#     Acquire `self.lock`. Return `list(self.clients.keys())` (R4).
#
# - `get_client_socket(username: str) -> socket.socket | None`:
#     Acquire `self.lock`. Return `self.clients.get(username)` for private message routing (R7).

# ==============================================================================
# TODO 3: Implement Group Management Methods (R8, R9, R10, R11)
# ==============================================================================
# - `create_group(group_name: str, creator_username: str) -> tuple[bool, str]`:
#     Acquire `self.lock`. Verify `group_name` does not already exist.
#     Create `self.groups[group_name] = {creator_username}` so it initially includes ONLY
#     the creator as a member (R8). Return `(True, "Group created")` or `(False, "Error reason")`.
#
# - `join_group(group_name: str, username: str) -> tuple[bool, str]`:
#     Acquire `self.lock`. Verify `group_name` exists in `self.groups`.
#     Add `username` to `self.groups[group_name]` (R10). Return success/error tuple.
#
# - `get_groups_with_members() -> dict[str, list[str]]`:
#     Acquire `self.lock`. Return `{group: list(members) for group, members in self.groups.items()}`
#     so every client can see all existing groups and their member lists (R9).
#
# - `get_group_member_sockets(group_name: str, sender_username: str) -> list[socket.socket]`:
#     Acquire `self.lock`. Verify `group_name` exists AND `sender_username` is a member of that group (R11).
#     Return the active sockets for all currently connected members of `group_name`.
