"""
Module: client/main.py
Purpose: Client Application Entry Point & High-Level GUI Controller
Mapped Requirements:
  - R1 (System Architecture): Runs as a standalone client process on any physical computer,
    connecting to the server's LAN IP and TCP port.
  - R3 (Unique Client Name): Coordinates the login handshake (`gui_login.py`) before transitioning
    to the main Lobby (`gui_lobby.py`).
"""

# ==============================================================================
# TODO 1: Import Standard Modules & Client Components
# ==============================================================================
# - Import `tkinter as tk`
# - Import `NetworkClient` from `client.network`
# - Import `LoginWindow` from `client.gui_login`
# - Import `LobbyWindow` from `client.gui_lobby`

# ==============================================================================
# TODO 2: Implement Application Controller / Entry Flow (`main()`)
# ==============================================================================
# 1. Create root Tkinter instance (`root = tk.Tk()`).
# 2. Instantiate `NetworkClient()` which manages the TCP socket and incoming `queue.Queue`.
# 3. Display `LoginWindow` first:
#      - User enters Server IP, Port, and desired unique Username (R3).
#      - Connect TCP socket and send `MSG_REGISTER`.
#      - If `MSG_REGISTER_ACK` returns `success=False` (duplicate username), show an error dialog
#        and let the user pick a different name (R3).
#      - If `MSG_REGISTER_ACK` returns `success=True`, transition from `LoginWindow` to `LobbyWindow`.
# 4. Start `root.mainloop()` and ensure socket cleanup on window close (`WM_DELETE_WINDOW`).

# ==============================================================================
# TODO 3: Implement CLI Entry Point (`if __name__ == "__main__":`)
# ==============================================================================
# - Call `main()`.
