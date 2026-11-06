"""
Module: client/main.py
Purpose: Client Application Entry Point & High-Level GUI Controller
"""

import tkinter as tk
from tkinter import ttk

from client.gui_login import LoginWindow
from client.network import NetworkClient


class LobbyWindow(ttk.Frame):
    """Temporary post-login view until the lobby requirement is implemented."""

    def __init__(self, parent: tk.Misc, network_client, username: str) -> None:
        super().__init__(parent, padding=24)
        ttk.Label(
            self,
            text=f"Connected as {username}",
            font=("Segoe UI", 14, "bold"),
        ).pack(pady=(0, 12))
        ttk.Label(self, text="Lobby will be implemented in the next requirement.").pack()


def main() -> None:
    root = tk.Tk()
    root.title("Network Chat")
    root.geometry("420x280")

    network_client = NetworkClient()
    login_window = None

    def show_lobby(username: str) -> None:
        nonlocal login_window
        if login_window is not None:
            login_window.destroy()
        lobby_window = LobbyWindow(root, network_client, username)
        lobby_window.pack(fill="both", expand=True)

    login_window = LoginWindow(root, network_client, show_lobby)
    login_window.pack(fill="both", expand=True)

    def on_close() -> None:
        network_client.disconnect()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
