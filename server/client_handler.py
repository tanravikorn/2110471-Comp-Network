"""
Module: server/client_handler.py
Purpose: Per-Client Worker Thread & Packet Router
Mapped Requirements:
  - R2 (Socket Programming Only): Reads/writes framed JSON messages over the client's TCP socket.
  - R3 (Unique Name): Handles initial `REGISTER` handshake before allowing chat operations.
  - R4 (Online Client List): Broadcasts updated `CLIENT_LIST` to all connected clients on join/leave.
  - R7 (Private Message): Routes `PRIVATE_MSG` exclusively to sender and receiver.
  - R8 (Create Group): Handles `CREATE_GROUP` request with creator as sole initial member.
  - R9 (Group List with Members): Broadcasts updated `GROUP_LIST` (with members) to all clients whenever a group is created or joined.
  - R10 (Self-Join Group): Handles `JOIN_GROUP` request initiated by the joining client itself.
  - R11 (Group Message): Routes `GROUP_MSG` exclusively to members of that group.
"""

# ==============================================================================
# TODO 1: Implement Broadcast Helpers
# ==============================================================================
# - `broadcast_client_list(state: ServerState) -> None`:
#     Build `{"type": MSG_CLIENT_LIST, "clients": state.get_client_list()}` and send to all connected sockets (R4).
#
# - `broadcast_group_list(state: ServerState) -> None`:
#     Build `{"type": MSG_GROUP_LIST, "groups": state.get_groups_with_members()}` and send to all connected sockets (R9).

# ==============================================================================
# TODO 2: Implement Per-Client Connection Lifecycle (`handle_client`)
# ==============================================================================
# - Function `handle_client(client_sock: socket.socket, client_addr: tuple, state: ServerState) -> None`:
#     1. Track `registered_username = None`.
#     2. Read newline-delimited JSON messages from `client_sock` in a loop:
#        a. If `registered_username is None`, only accept `MSG_REGISTER` (R3):
#           - Call `state.register_client(username, client_sock)`.
#           - If accepted: set `registered_username`, send `MSG_REGISTER_ACK (success=True)`,
#             then call `broadcast_client_list(state)` (R4) and send current `MSG_GROUP_LIST` (R9).
#           - If rejected (duplicate name): send `MSG_REGISTER_ACK (success=False, message="Name taken")`
#             and allow the client to retry with a new name.
#        b. Once registered, dispatch by `msg["type"]`:
#           - `MSG_PRIVATE` (R7):
#               Extract `to` and `text`. Look up receiver socket in `state`.
#               Send packet ONLY to the receiver socket and echo/confirm to sender socket.
#           - `MSG_CREATE_GROUP` (R8, R9):
#               Extract `group`. Call `state.create_group(group, registered_username)`.
#               If created, call `broadcast_group_list(state)` so all clients see the new group & member list.
#           - `MSG_JOIN_GROUP` (R9, R10):
#               Extract `group`. Call `state.join_group(group, registered_username)`.
#               If joined, call `broadcast_group_list(state)` so all clients see the updated member list.
#           - `MSG_GROUP` (R11):
#               Extract `group` and `text`. Verify `registered_username` is a member of `group`.
#               Send packet ONLY to sockets of members in `group`.
#     3. In `finally:` block (on client disconnect or socket error):
#        - If `registered_username` was set, remove from `state`, close `client_sock`,
#          and broadcast updated `CLIENT_LIST` (R4) and `GROUP_LIST` (R9).
