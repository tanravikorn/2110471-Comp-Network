"""
Module: client/gui_login.py
Purpose: Tkinter login screen and R3 username registration handshake.
"""

import queue
import tkinter as tk
from tkinter import ttk
from typing import Callable

from common.protocol import (
    DEFAULT_PORT,
    ERR_USERNAME_TAKEN,
    MSG_ERROR,
    MSG_REGISTER_ACK,
)


class LoginWindow(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        network_client,
        on_login_success: Callable[[str], None],
    ) -> None:
        super().__init__(parent, padding=24)
        self.network_client = network_client
        self.on_login_success = on_login_success
        self._polling = False
        self._pending_username = ""
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="Server IP").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=4)
        self.host_entry = ttk.Entry(self, width=28)
        self.host_entry.insert(0, "127.0.0.1")
        self.host_entry.grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(self, text="Port").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=4)
        self.port_entry = ttk.Entry(self, width=28)
        self.port_entry.insert(0, str(DEFAULT_PORT))
        self.port_entry.grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(self, text="Username").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=4)
        self.username_entry = ttk.Entry(self, width=28)
        self.username_entry.grid(row=2, column=1, sticky="ew", pady=4)
        self.username_entry.bind("<Return>", lambda _event: self.connect_and_join())

        self.status_label = ttk.Label(self, text="", foreground="#b00020")
        self.status_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 4))

        self.connect_button = ttk.Button(self, text="Connect & Join", command=self.connect_and_join)
        self.connect_button.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 0))

    def set_status(self, text: str, error: bool = True) -> None:
        self.status_label.configure(text=text, foreground="#b00020" if error else "#207520")

    def connect_and_join(self) -> None:
        host = self.host_entry.get().strip()
        port_text = self.port_entry.get().strip()
        username = self.username_entry.get().strip()

        if not host:
            self.set_status("Server IP is required.")
            return
        if not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
            self.set_status("Port must be a number from 1 to 65535.")
            return
        if not username:
            self.set_status("Username is required.")
            return

        if not self.network_client.connected:
            ok, message = self.network_client.connect(host, int(port_text))
            if not ok:
                self.set_status(f"Connection failed: {message}")
                return

        self.connect_button.configure(state="disabled")
        self.set_status("Registering username...", error=False)
        self._pending_username = username

        if not self.network_client.send_register(username):
            self.connect_button.configure(state="normal")
            self.set_status("Could not send the registration request.")
            return

        if not self._polling:
            self._polling = True
            self.after(100, self.poll_registration)

    def poll_registration(self) -> None:
        if not self.winfo_exists():
            return

        try:
            while True:
                msg = self.network_client.incoming_queue.get_nowait()
                msg_type = msg.get("type")
                payload = msg.get("payload", {})

                if msg_type == MSG_REGISTER_ACK:
                    if payload.get("success") is True:
                        self.network_client.username = self._pending_username
                        self._polling = False
                        self.on_login_success(self._pending_username)
                        return

                    message = payload.get("message", "Username is not available.")
                    self.set_status(message)
                    self.connect_button.configure(state="normal")
                    self.username_entry.focus_set()
                    self.username_entry.select_range(0, tk.END)
                    self._polling = False
                    return

                if msg_type == MSG_ERROR and payload.get("code") == ERR_USERNAME_TAKEN:
                    self.set_status(payload.get("message", "Username is already taken."))
                    self.connect_button.configure(state="normal")
                    self.username_entry.focus_set()
                    self.username_entry.select_range(0, tk.END)
                    self._polling = False
                    return

                if msg_type in ("DISCONNECT", "DISCONNECTED"):
                    self.set_status("Disconnected from the server.")
                    self.connect_button.configure(state="normal")
                    self._polling = False
                    return
        except queue.Empty:
            pass

        if self._polling:
            self.after(100, self.poll_registration)
