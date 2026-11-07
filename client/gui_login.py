"""
Module: client/gui_login.py
Purpose: Tkinter Login & Server Connection Dialog
Mapped Requirements:
  - R1 (System Architecture): Allows specifying the Server IP address and TCP Port so clients
    on separate physical computers can connect over LAN or Cloud VPS.
  - R3 (Unique Client Name): Prompts the user for a unique client name, validates input,
    sends the REGISTER packet, and displays an error if the server reports that the name
    is already taken by another connected client.
"""

import queue
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional

from common.protocol import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    ERR_USERNAME_TAKEN,
    KEY_PAYLOAD,
    KEY_TIMESTAMP,
    KEY_TYPE,
    MSG_ERROR,
    MSG_REGISTER,
    MSG_REGISTER_ACK,
)


class LoginWindow(ttk.Frame):
    """
    Login & Server Connection Dialog Frame (R1, R3).

    Handles:
      1. Server IP and Port inputs for LAN / Cloud VPS TCP connection (R1).
      2. Unique username input and validation (R3).
      3. Transmitting REGISTER packet to the server.
      4. Polling incoming queue for REGISTER_ACK or duplicate username error (R3).
      5. Invoking on_login_success callback upon successful registration.
    """

    def __init__(
        self,
        parent: tk.Misc,
        network_client: Any,
        on_login_success: Callable[[str], None],
    ) -> None:
        super().__init__(parent, padding=24)
        self.network_client = network_client
        self.on_login_success = on_login_success

        self._polling: bool = False
        self._pending_username: str = ""
        self._connected_host: Optional[str] = None
        self._connected_port: Optional[int] = None
        self._poll_attempts: int = 0

        self._build_ui()

    def _build_ui(self) -> None:
        """Constructs UI widgets for Server IP, Port, Username, and Actions."""
        self.columnconfigure(1, weight=1)

        # Title Label
        title_label = ttk.Label(
            self,
            text="Join Chat Server",
            font=("Segoe UI", 12, "bold"),
        )
        title_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 16))

        # 1. Server IP Entry (R1)
        ttk.Label(self, text="Server IP:").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=6)
        self.host_entry = ttk.Entry(self, width=28)
        self.host_entry.insert(0, "127.0.0.1")
        self.host_entry.grid(row=1, column=1, sticky="ew", pady=6)
        self.host_entry.bind("<Return>", lambda _e: self.port_entry.focus_set())

        # 2. Server Port Entry (R1)
        ttk.Label(self, text="Port:").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=6)
        self.port_entry = ttk.Entry(self, width=28)
        self.port_entry.insert(0, str(DEFAULT_PORT))
        self.port_entry.grid(row=2, column=1, sticky="ew", pady=6)
        self.port_entry.bind("<Return>", lambda _e: self.username_entry.focus_set())

        # 3. Unique Username Entry (R3)
        ttk.Label(self, text="Username:").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=6)
        self.username_entry = ttk.Entry(self, width=28)
        self.username_entry.grid(row=3, column=1, sticky="ew", pady=6)
        self.username_entry.bind("<Return>", lambda _e: self.connect_and_join())

        # 4. Status / Feedback Label
        self.status_label = ttk.Label(
            self,
            text="",
            foreground="#b00020",
            wraplength=320,
            justify="left",
        )
        self.status_label.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 6))

        # 5. Connect & Join Button
        self.connect_button = ttk.Button(
            self,
            text="Connect & Join",
            command=self.connect_and_join,
        )
        self.connect_button.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        # Focus username field by default
        self.username_entry.focus_set()

    def set_status(self, text: str, error: bool = True) -> None:
        """Updates the feedback label with colored status message."""
        color = "#b00020" if error else "#207520"
        self.status_label.configure(text=text, foreground=color)

    def _send_register_packet(self, username: str) -> bool:
        """
        Encodes and transmits MSG_REGISTER envelope to the server socket (R3).
        Supports either send_register() helper or raw send_packet().
        """
        try:
            if hasattr(self.network_client, "send_register") and callable(getattr(self.network_client, "send_register")):
                self.network_client.send_register(username)
                return getattr(self.network_client, "connected", False)
            else:
                self.network_client.send_packet(MSG_REGISTER, {"username": username})
                return getattr(self.network_client, "connected", False)
        except Exception as exc:
            self.set_status(f"Socket send error: {exc}", error=True)
            return False

    def connect_and_join(self) -> None:
        """
        Validates inputs, connects to server if needed, and initiates registration (R1, R3).
        """
        if self._polling:
            return

        host = self.host_entry.get().strip()
        port_text = self.port_entry.get().strip()
        username = self.username_entry.get().strip()

        # Validate inputs
        if not host:
            self.set_status("Server IP is required.", error=True)
            self.host_entry.focus_set()
            return

        if not port_text.isdigit() or not (1 <= int(port_text) <= 65535):
            self.set_status("Port must be a number from 1 to 65535.", error=True)
            self.port_entry.focus_set()
            return
        port = int(port_text)

        if not username:
            self.set_status("Username is required.", error=True)
            self.username_entry.focus_set()
            return

        # Check / establish TCP socket connection (R1)
        is_connected = getattr(self.network_client, "connected", False)
        if is_connected and self._connected_host is not None and (self._connected_host, self._connected_port) != (host, port):
            if hasattr(self.network_client, "disconnect") and callable(getattr(self.network_client, "disconnect")):
                self.network_client.disconnect()
            is_connected = False

        if not is_connected:
            self.set_status(f"Connecting to {host}:{port}...", error=False)
            self.update_idletasks()
            if hasattr(self.network_client, "connect") and callable(getattr(self.network_client, "connect")):
                ok, message = self.network_client.connect(host, port)
                if not ok:
                    self.set_status(f"Connection failed: {message}", error=True)
                    self.connect_button.configure(state="normal")
                    return
            self._connected_host = host
            self._connected_port = port
        elif self._connected_host is None:
            self._connected_host = host
            self._connected_port = port

        # Transmit registration request (R3)
        self.connect_button.configure(state="disabled")
        self.set_status("Registering username...", error=False)
        self._pending_username = username

        if not self._send_register_packet(username):
            self.connect_button.configure(state="normal")
            self.set_status("Could not send the registration request.", error=True)
            return

        # Begin polling background queue for server verification
        self._poll_attempts = 0
        if not self._polling:
            self._polling = True
            self.after(50, self.poll_registration)

    def poll_registration(self) -> None:
        """
        Polls the thread-safe incoming_queue for server response (R3).
        Drives the validation handshake:
          - MSG_REGISTER_ACK with success=True -> on_login_success
          - MSG_REGISTER_ACK with success=False -> displays rejection reason
          - MSG_ERROR with USERNAME_TAKEN -> displays duplicate username error
        """
        if not self.winfo_exists():
            return

        terminal_event = False

        try:
            while True:
                msg = self.network_client.incoming_queue.get_nowait()
                msg_type = msg.get(KEY_TYPE)
                payload = msg.get(KEY_PAYLOAD, {})

                if msg_type == MSG_REGISTER_ACK:
                    terminal_event = True
                    self._polling = False
                    success = payload.get("success")
                    status = payload.get("status")

                    if success is True or status == "SUCCESS":
                        self.network_client.username = self._pending_username
                        self.set_status(payload.get("message", "Registration successful!"), error=False)
                        self.on_login_success(self._pending_username)
                        return
                    else:
                        # R3: Server rejected duplicate or invalid username
                        rejection_msg = payload.get("message", "Username is already taken. Please choose another.")
                        self.set_status(rejection_msg, error=True)
                        self.connect_button.configure(state="normal")
                        self.username_entry.focus_set()
                        self.username_entry.select_range(0, tk.END)
                        return

                elif msg_type == MSG_ERROR:
                    terminal_event = True
                    self._polling = False
                    code = payload.get("code")
                    if code == ERR_USERNAME_TAKEN:
                        err_msg = payload.get("message", "Username is already taken.")
                    else:
                        err_msg = payload.get("message", "An error occurred during registration.")
                    self.set_status(err_msg, error=True)
                    self.connect_button.configure(state="normal")
                    self.username_entry.focus_set()
                    self.username_entry.select_range(0, tk.END)
                    return

                elif msg_type in ("DISCONNECTED", "DISCONNECT"):
                    terminal_event = True
                    self._polling = False
                    self.set_status("Disconnected from the server.", error=True)
                    self.connect_button.configure(state="normal")
                    return

                else:
                    # Pre-registration messages (e.g. initial CLIENT_LIST broadcast)
                    # are ignored because server broadcasts fresh CLIENT_LIST upon registration
                    pass

        except queue.Empty:
            pass

        if not terminal_event and self._polling:
            self._poll_attempts += 1
            if self._poll_attempts > 100:  # ~10 second timeout (100 * 100ms)
                self._polling = False
                self.set_status("Registration timed out: server did not respond.", error=True)
                self.connect_button.configure(state="normal")
                return
            self.after(100, self.poll_registration)
