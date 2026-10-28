"""
Module: client/gui_chatroom.py
Purpose: Dedicated Tkinter Toplevel Window for a Single Private or Group Chat Room
Mapped Requirements:
  - R5 (Own Chat Room): Each chat between clients (both Private and Group message) has its
    own independent chat room window (`tk.Toplevel`).
  - R6 (Chat Box & Chat Window): Includes a scrollable chat window (`ScrolledText` or `Text` + `Scrollbar`)
    for displaying sent and incoming messages, and a chat box (`Entry` + Send `Button`) for sending text messages.
  - R7 (Private Message): Sends direct text messages to a specific peer; displays messages only in this room.
  - R11 (Group Message): Sends text messages to a joined group; displays messages from group members.
"""

# ==============================================================================
# TODO 1: Define `ChatRoomWindow` Class (`tk.Toplevel`)
# ==============================================================================
# - Constructor parameters:
#     - `parent`: parent Tkinter widget (`LobbyWindow` / `root`)
#     - `room_type`: `"PRIVATE"` or `"GROUP"`
#     - `target_name`: peer's username (for `"PRIVATE"`) or group name (for `"GROUP"`)
#     - `own_username`: the current client's username
#     - `on_send_callback`: function `(text: str) -> None` that calls either
#       `network.send_private_message(target_name, text)` (R7) or
#       `network.send_group_message(target_name, text)` (R11)
#     - `on_close_callback`: function to notify `LobbyWindow` when this window is closed/hidden

# ==============================================================================
# TODO 2: Build Chat Room UI Components (R5, R6)
# ==============================================================================
# 1. Window Title & Header Banner:
#      - For Private room: `"Private Chat with <target_name> — (<own_username>)"`
#      - For Group room: `"Group Chat: <target_name> — Members: [...]"`
# 2. Chat Window (Message Display Area — R6):
#      - Read-only `tkinter.scrolledtext.ScrolledText` (state=`"disabled"`, enabled briefly when appending).
#      - Displays both sent messages (e.g., `"[You]: Hello"`) and incoming messages (`"[Alice]: Hi"`).
# 3. Chat Box (Message Input Area — R6):
#      - Bottom frame containing a text input box (`tk.Entry`) and a `"Send"` button (`tk.Button`).
#      - Bind `<Return>` (Enter key) on the `tk.Entry` to trigger message sending.

# ==============================================================================
# TODO 3: Implement Message Display & Send Handlers (R6, R7, R11)
# ==============================================================================
# - `on_send() -> None`:
#     Read text from the input box, strip whitespace. If non-empty:
#     Invoke `self.on_send_callback(text)` and clear the input box.
#
# - `append_message(sender: str, text: str) -> None`:
#     Unlock the `ScrolledText` widget (`state="normal"`), insert formatted line
#     (highlighting `"You"` if `sender == self.own_username`), scroll to bottom (`see("end")`),
#     and re-lock (`state="disabled"`).
#
# - `update_group_members(members: list[str]) -> None`:
#     (For Group rooms) Update the header label when new members join the group (R9, R10).
