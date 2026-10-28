"""
Module: client/gui_lobby.py
Purpose: Main Tkinter Lobby Window (Connected Clients List, Group List, & Room Launcher)
Mapped Requirements:
  - R4 (Connected Client List): Displays a live list of all currently connected clients,
    explicitly including the client's own name (e.g., `"Alice (You)"`).
  - R5 (Separate Chat Rooms): Opens and manages dedicated `ChatRoomWindow` (`tk.Toplevel`)
    instances for each Private chat peer and each joined Group chat.
  - R8 (Create Group): Provides UI input/button to create a new chat group (creator is sole initial member).
  - R9 (Group List with Members): Displays all existing chat groups created by any client,
    along with each group's current member list.
  - R10 (Self-Join Group): Provides a "Join Group" button allowing the client to join a selected
    group by themselves (never added automatically by the creator).
"""

# ==============================================================================
# TODO 1: Define `LobbyWindow` Layout & State
# ==============================================================================
# - State dictionaries to track open chat room windows (R5):
#     - `self.private_rooms: dict[str, ChatRoomWindow] = {}`  # maps peer_username -> ChatRoomWindow
#     - `self.group_rooms: dict[str, ChatRoomWindow] = {}`    # maps group_name -> ChatRoomWindow
#     - `self.groups_data: dict[str, list[str]] = {}`         # latest group -> member list mapping (R9)
#
# - Left Panel — Connected Clients (R4, R5, R7):
#     - Header label showing own username.
#     - `tk.Listbox` or `ttk.Treeview` listing all connected clients (including own name, R4).
#     - "Open Private Chat" button (or double-click binding) to open/focus the 1-to-1
#       `ChatRoomWindow` with the selected peer (R5, R7).
#
# - Right Panel — Chat Groups & Member Lists (R8, R9, R10, R11):
#     - `ttk.Treeview` or `tk.Listbox` showing every existing group name AND its member list (R9).
#     - Entry + "Create Group" button: sends `MSG_CREATE_GROUP` to server (R8).
#     - "Join Selected Group" button: sends `MSG_JOIN_GROUP` for the selected group so the client
#       joins by themselves (R10).
#     - "Open Group Chat" button: if the client is a member of the selected group, opens/focuses
#       the group's `ChatRoomWindow` (R5, R11).

# ==============================================================================
# TODO 2: Implement Queue Polling & Incoming Event Dispatcher (`poll_incoming_queue`)
# ==============================================================================
# - Schedule `self.root.after(100, self.poll_incoming_queue)` to process events from `network_client.incoming_queue`:
#     - `MSG_CLIENT_LIST` (R4):
#         Refresh the Connected Clients list UI, ensuring own username is included.
#     - `MSG_GROUP_LIST` (R9):
#         Update `self.groups_data` and refresh the Groups + Member Lists UI.
#         Also update member list header in any open `group_rooms`.
#     - `MSG_PRIVATE` (R5, R6, R7):
#         Determine the peer username (`from` if incoming, `to` if echoed sent message).
#         If `self.private_rooms[peer]` is not open yet, automatically create/open its `ChatRoomWindow` (R5).
#         Append the message to that room's chat display window (R6).
#     - `MSG_GROUP` (R5, R6, R11):
#         Extract `group`, `from`, and `text`.
#         If `self.group_rooms[group]` is not open yet, create/open its `ChatRoomWindow` (R5).
#         Append the message to that group room's chat display window (R6).
#     - `MSG_ERROR`:
#         Display warning/error messagebox to the user.
