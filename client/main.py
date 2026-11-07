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

import queue
import sys
import tkinter as tk

from client.gui_lobby import LobbyWindow
from client.gui_login import LoginWindow
from client.network import NetworkClient

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

def main():
    # 1. Create main Tkinter root window
    root = tk.Tk()
    root.title("Network Chat — Login")
    root.geometry("400x320")
    root.resizable(False, False)

    # Bring window to front on macOS / VS Code
    root.lift()
    root.attributes("-topmost", True)
    root.after_idle(root.attributes, "-topmost", False)

    # 2. Instantiate NetworkClient (creates thread-safe incoming_queue internally)
    client = NetworkClient()

    # Clean disconnection handler on window exit
    def on_closing():
        client.disconnect()
        root.destroy()
        sys.exit(0)

    root.protocol("WM_DELETE_WINDOW", on_closing)

    # 3. Transition callback called when LoginWindow succeeds (R3 -> Lobby)
    def on_login_success(username: str):
        # Remove Login frame
        login_frame.destroy()

        # Update window dimensions & title for Lobby
        root.title(f"Network Chat — Logged in as {username}")
        root.geometry("750x500")
        root.resizable(True, True)

        # Launch main LobbyWindow (R4, R5, R8-R11)
        lobby_frame = LobbyWindow(
            parent=root,
            own_username=username,
            network_client=client,
        )
        lobby_frame.pack(fill="both", expand=True)

    # 4. Display LoginWindow first (R1, R3)
    login_frame = LoginWindow(
        parent=root,
        network_client=client,
        on_login_success=on_login_success,
    )
    login_frame.pack(fill="both", expand=True)

    # 5. Start Tkinter event loop
    root.mainloop()
        
# ==============================================================================
# TODO 3: Implement CLI Entry Point (`if __name__ == "__main__":`)
# ==============================================================================
# - Call `main()`.

if __name__ == "__main__":
    main()
