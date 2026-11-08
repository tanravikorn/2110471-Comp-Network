"""
Module: client/gui_chatroom.py
Purpose: Reusable Tkinter Toplevel Chat Room Window UI Component for Requirements R5 and R6
Mapped Requirements:
  - R5 (Separate Chat Rooms): Dedicated chat room window (`tk.Toplevel`).
  - R6 (Chat Box & Chat Window): Read-only ScrolledText message display & Entry input box.
  - B1 (AI Summary): Request button, loading state, and formatted AI conversation summary card.
  - B3 (Typing Indicator): Real-time multi-user typing status rendered directly inside chat history stream.
  - B4 (Voice Messages): Push-to-talk voice clip recording, Base64 transmission, replay, and playback.
"""

from __future__ import annotations

import base64
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import scrolledtext, ttk
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.protocol import (
    MSG_AI_SUMMARY_REQ,
    MSG_GROUP,
    MSG_PRIVATE,
    MSG_TYPING,
    MSG_VOICE_MSG,
    ROOM_GROUP,
    ROOM_PRIVATE,
    get_current_timestamp,
)


class ChatRoomWindow(tk.Toplevel):
    """
    Dedicated Tkinter Toplevel window representing a single chat room.
    Supports both 1-on-1 Private chats and multi-user Group chats (R5).
    """

    def __init__(
        self,
        parent: Optional[tk.Misc] = None,
        room_type: str = ROOM_PRIVATE,
        target_name: str = "Chat",
        own_username: str = "You",
        network_client: Optional[Any] = None,
        on_close_callback: Optional[Callable[..., None]] = None,
        on_send_message_callback: Optional[Callable[[str, str], None]] = None,
        on_voice_sent_callback: Optional[Callable[..., None]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent)

        if (
            callable(network_client)
            and not hasattr(network_client, "send_packet")
            and on_send_message_callback is None
        ):
            on_send_message_callback = network_client
            network_client = None

        if "on_send_message_callback" in kwargs and on_send_message_callback is None:
            on_send_message_callback = kwargs["on_send_message_callback"]
        if "on_close_callback" in kwargs and on_close_callback is None:
            on_close_callback = kwargs["on_close_callback"]
        if "on_voice_sent_callback" in kwargs and on_voice_sent_callback is None:
            on_voice_sent_callback = kwargs["on_voice_sent_callback"]

        self.room_type = room_type
        self.target_name = target_name
        self.own_username = own_username
        self.network_client = network_client
        self.on_close_callback = on_close_callback
        self.on_send_message_callback = on_send_message_callback
        self.on_voice_sent_callback = on_voice_sent_callback

        # Real-time typing status state (B3)
        self._typing_timer: Optional[str] = None
        self._is_typing_active: bool = False
        self._active_typers: set[str] = set()  # Multi-user typing set

        # Voice message recording state (B4)
        self._is_recording_voice: bool = False
        self._voice_start_time: float = 0.0
        self._temp_voice_file: str = ""
        self._voice_auto_stop_timer: Optional[str] = None
        self._stream: Optional[Any] = None

        # AI Summary request state (B1)
        self._is_requesting_summary: bool = False
        self._summary_timeout_job: Optional[str] = None

        # Thread-safe UI dispatch queue
        self._ui_queue: queue.Queue[Tuple[Callable[..., Any], Tuple[Any, ...]]] = queue.Queue()
        self._poll_job: Optional[str] = None

        # State tracking (R5 presence & participant list)
        self._is_online: bool = True
        self._participants: List[str] = [own_username]
        if room_type == ROOM_PRIVATE and target_name:
            self._participants.append(target_name)

        # Configure window properties
        self._update_window_title()
        self.geometry("560x600")
        self.minsize(460, 460)

        # Handle window close protocol (WM_DELETE_WINDOW)
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # Build UI layout & tags (R6, B1, B3, B4)
        self._build_ui()
        self._configure_tags()

        # Start thread-safe UI queue polling
        self._poll_ui_queue()

    # =========================================================================
    # Thread-Safe Dispatch Mechanism
    # =========================================================================

    def _poll_ui_queue(self) -> None:
        """Polls queue for actions dispatched from background threads."""
        try:
            if not self.winfo_exists():
                return
            while not self._ui_queue.empty():
                try:
                    fn, args = self._ui_queue.get_nowait()
                    fn(*args)
                except Exception:
                    break
            if self.winfo_exists():
                self._poll_job = self.after(50, self._poll_ui_queue)
        except Exception:
            pass

    def _run_on_ui_thread(self, fn: Callable[..., Any], *args: Any) -> None:
        """Executes function immediately if on main thread, else enqueues it."""
        if threading.current_thread() is threading.main_thread():
            fn(*args)
        else:
            self._ui_queue.put((fn, args))

    # =========================================================================
    # UI Layout & Widget Creation (R5, R6, B1, B4)
    # =========================================================================

    def _build_ui(self) -> None:
        """Constructs all GUI sub-components for R5, R6, B1, and B4."""
        self.configure(bg="#F4F6F9")

        # 1. Title Header Bar (R5)
        self.header_frame = tk.Frame(self, bg="#FFFFFF", padx=14, pady=10, relief="groove", bd=1)
        self.header_frame.pack(side="top", fill="x")

        self.title_info_frame = tk.Frame(self.header_frame, bg="#FFFFFF")
        self.title_info_frame.pack(side="left", fill="x", expand=True)

        room_icon = "👤" if self.room_type == ROOM_PRIVATE else "👥"
        self.header_title_label = tk.Label(
            self.title_info_frame,
            text=f"{room_icon} {self.target_name}",
            font=("Segoe UI", 12, "bold"),
            bg="#FFFFFF",
            fg="#1A202C",
            anchor="w",
        )
        self.header_title_label.pack(anchor="w")

        self.header_subtitle_label = tk.Label(
            self.title_info_frame,
            text=self._format_subtitle(),
            font=("Segoe UI", 9),
            bg="#FFFFFF",
            fg="#718096",
            anchor="w",
        )
        self.header_subtitle_label.pack(anchor="w", pady=(2, 0))

        # 2. Chat Display Area (R6 Chat Window)
        self.chat_display_frame = tk.Frame(self, bg="#F4F6F9", padx=10, pady=8)
        self.chat_display_frame.pack(side="top", fill="both", expand=True)

        self.chat_display = scrolledtext.ScrolledText(
            self.chat_display_frame,
            wrap=tk.WORD,
            state="disabled",
            font=("Segoe UI", 10),
            bg="#FFFFFF",
            fg="#2D3748",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#CBD5E0",
            highlightcolor="#3182CE",
            padx=10,
            pady=10,
        )
        self.chat_display.pack(fill="both", expand=True)

        # 3. Message Input Area (R6 Chat Box, B4 Voice Button, & B1 AI Summary Button)
        self.input_frame = tk.Frame(self, bg="#FFFFFF", padx=10, pady=10, relief="groove", bd=1)
        self.input_frame.pack(side="bottom", fill="x")

        self.message_entry = ttk.Entry(
            self.input_frame,
            font=("Segoe UI", 10),
        )
        self.message_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        # Keypress & Return bindings (R6, B3)
        self.message_entry.bind("<Key>", self._on_key_press)
        self.message_entry.bind("<Return>", self._on_return)

        self.send_button = ttk.Button(
            self.input_frame,
            text="Send",
            command=self.send_message,
        )
        self.send_button.pack(side="right")

        # Voice Message Button (B4)
        self.voice_button = ttk.Button(
            self.input_frame,
            text="🎤 Record Voice",
            command=self._toggle_voice_recording,
        )
        self.voice_button.pack(side="right", padx=(0, 4))

        # AI Summary Button (B1) placed next to Voice Message Button
        self.ai_summary_button = ttk.Button(
            self.input_frame,
            text="✨ AI Summary",
            command=self.request_ai_summary,
        )
        self.ai_summary_button.pack(side="right", padx=(0, 4))

        self._focus_job: Optional[str] = self.after(50, self._focus_entry)

    def _focus_entry(self) -> None:
        """Helper to safely focus input entry if window still exists."""
        if self.winfo_exists():
            self.message_entry.focus_set()

    def _configure_tags(self) -> None:
        """Configures Tkinter text tags for formatting message styles (R6, B1, B3, B4)."""
        for tag in ("self_header", "own_header"):
            self.chat_display.tag_config(
                tag,
                justify="right",
                foreground="#1976D2",
                font=("Segoe UI", 9, "bold"),
                rmargin=12,
                lmargin1=60,
                lmargin2=60,
            )

        for tag in ("self_msg", "own_msg", "self", "own"):
            self.chat_display.tag_config(
                tag,
                justify="right",
                foreground="#0D47A1",
                font=("Segoe UI", 10),
                rmargin=12,
                lmargin1=60,
                lmargin2=60,
            )

        self.chat_display.tag_config(
            "other_header",
            justify="left",
            foreground="#2E7D32",
            font=("Segoe UI", 9, "bold"),
            lmargin1=12,
            lmargin2=12,
            rmargin=60,
        )
        for tag in ("other_msg", "other"):
            self.chat_display.tag_config(
                tag,
                justify="left",
                foreground="#212121",
                font=("Segoe UI", 10),
                lmargin1=12,
                lmargin2=12,
                rmargin=60,
            )

        for tag in ("system", "system_msg"):
            self.chat_display.tag_config(
                tag,
                justify="center",
                foreground="#757575",
                font=("Segoe UI", 9, "italic"),
                spacing1=3,
                spacing3=3,
            )

        self.chat_display.tag_config(
            "timestamp",
            foreground="#888888",
            font=("Segoe UI", 8),
        )

        # Real-time Multi-User Typing Indicator tag (B3)
        self.chat_display.tag_config(
            "typing_indicator",
            justify="left",
            foreground="#3182CE",
            font=("Segoe UI", 9, "italic"),
            lmargin1=12,
            lmargin2=12,
        )

        # Temporary Recording Status Indicator tag (B4)
        self.chat_display.tag_config(
            "recording_status",
            justify="center",
            foreground="#757575",
            font=("Segoe UI", 9, "italic"),
            spacing1=3,
            spacing3=3,
        )

        # AI Conversation Summary tags (B1)
        self.chat_display.tag_config(
            "ai_summary_status",
            justify="center",
            foreground="#6B46C1",
            font=("Segoe UI", 9, "italic"),
            spacing1=3,
            spacing3=3,
        )
        self.chat_display.tag_config(
            "ai_summary_header",
            justify="left",
            foreground="#4C51BF",
            background="#EBF4FF",
            font=("Segoe UI", 9, "bold"),
            lmargin1=16,
            lmargin2=16,
            rmargin=16,
            spacing1=6,
            spacing3=2,
        )
        self.chat_display.tag_config(
            "ai_summary_body",
            justify="left",
            foreground="#2D3748",
            background="#F7FAFC",
            font=("Segoe UI", 10),
            lmargin1=16,
            lmargin2=16,
            rmargin=16,
            spacing1=2,
            spacing3=6,
        )

    # =========================================================================
    # Header & Presence Helpers (R5)
    # =========================================================================

    def _format_subtitle(self) -> str:
        """Formats subtitle string based on room type and presence."""
        if self.room_type == ROOM_PRIVATE:
            status = "Online" if self._is_online else "Offline"
            return f"Direct Message • {status}"
        count = len(self._participants) if self._participants else 1
        return f"Group Chat • {count} member{'s' if count != 1 else ''}"

    def _update_window_title(self) -> None:
        """Sets the OS window title."""
        if self.room_type == ROOM_PRIVATE:
            self.title(f"Private Chat: {self.target_name} ({self.own_username})")
        else:
            self.title(f"Group Chat: {self.target_name} ({self.own_username})")

    def set_online_status(self, is_online: bool) -> None:
        """Updates the online presence status for private chat (thread-safe)."""
        def _update():
            if not self.winfo_exists():
                return
            self._is_online = is_online
            self.header_subtitle_label.configure(text=self._format_subtitle())

        self._run_on_ui_thread(_update)

    def set_participants(self, participants: List[str]) -> None:
        """Updates the participant list for group chat (thread-safe)."""
        def _update():
            if not self.winfo_exists():
                return
            self._participants = list(participants)
            self.header_subtitle_label.configure(text=self._format_subtitle())

        self._run_on_ui_thread(_update)

    def update_header(
        self,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
    ) -> None:
        """Directly updates title/subtitle of header (thread-safe)."""
        def _update():
            if not self.winfo_exists():
                return
            if title is not None:
                self.target_name = title
                room_icon = "👤" if self.room_type == ROOM_PRIVATE else "👥"
                self.header_title_label.configure(text=f"{room_icon} {title}")
                self._update_window_title()
            if subtitle is not None:
                self.header_subtitle_label.configure(text=subtitle)

        self._run_on_ui_thread(_update)

    def bring_to_front(self) -> None:
        """Restores and focuses the window (thread-safe)."""
        def _focus():
            if not self.winfo_exists():
                return
            self.deiconify()
            self.lift()
            self.message_entry.focus_set()

        self._run_on_ui_thread(_focus)

    def show_error(self, message: str) -> None:
        """Displays a system error notice in the chat (thread-safe)."""
        self.display_message("System", f"⚠ {message}", is_system=True)

    # =========================================================================
    # Message Display & Formatting (R5, R6)
    # =========================================================================

    def display_message(
        self,
        sender: str,
        message: str,
        timestamp: str = "",
        is_self: bool = False,
        is_system: bool = False,
    ) -> None:
        """Appends a message to the chat display in a thread-safe manner (R6)."""
        self._run_on_ui_thread(
            self._display_message_main,
            sender,
            message,
            timestamp,
            is_self,
            is_system,
        )

    def append_message(self, sender: str, text: str, timestamp: str = "") -> None:
        """Alias for display_message matching LobbyWindow dispatcher (R6)."""
        is_self = (sender == self.own_username)
        self.display_message(
            sender=sender,
            message=text,
            timestamp=timestamp,
            is_self=is_self,
            is_system=False,
        )

    def render_history(self, history: List[Dict[str, Any]]) -> None:
        """Renders recorded history at top without deleting live messages or voice clips (B1, B4)."""
        def _render():
            if not self.winfo_exists():
                return

            if getattr(self, "_history_rendered", False):
                return
            self._history_rendered = True

            self.chat_display.configure(state="normal")
            existing_text = self.chat_display.get("1.0", tk.END)

            for item in reversed(history):
                if not isinstance(item, dict):
                    continue
                sender = str(item.get("sender", "System")).strip() or "System"
                text = str(item.get("text", "")).strip()
                timestamp = str(item.get("timestamp", "")).strip()
                if not text:
                    continue

                if text in existing_text:
                    continue

                is_self = sender.lower() == self.own_username.lower()
                ts_str = f" • {timestamp}" if timestamp else ""

                if is_self:
                    self.chat_display.insert("1.0", f"{text}\n\n", ("self_msg", "own_msg"))
                    self.chat_display.insert("1.0", f"You{ts_str}\n", ("self_header", "own_header"))
                else:
                    self.chat_display.insert("1.0", f"{text}\n\n", ("other_msg",))
                    self.chat_display.insert("1.0", f"{sender}{ts_str}\n", ("other_header",))

            self.chat_display.configure(state="disabled")
            self.chat_display.see(tk.END)

        self._run_on_ui_thread(_render)

    def _display_message_main(
        self,
        sender: str,
        message: str,
        timestamp: str = "",
        is_self: bool = False,
        is_system: bool = False,
    ) -> None:
        """Internal main-thread implementation of message display (R6)."""
        if not self.winfo_exists():
            return

        if not timestamp:
            timestamp = get_current_timestamp()

        if sender == self.own_username or sender.lower() == self.own_username.lower() or sender == "You":
            is_self = True

        if hasattr(self, "_active_typers"):
            self._active_typers.discard(sender)

        self.chat_display.configure(state="normal")

        ranges = self.chat_display.tag_ranges("typing_indicator")
        if ranges:
            self.chat_display.delete(ranges[0], ranges[1])

        if is_system:
            ts_str = f"[{timestamp}] " if timestamp else ""
            self.chat_display.insert(tk.END, f"{ts_str}{message}\n\n", ("system", "system_msg"))
        elif is_self:
            ts_str = f" • {timestamp}" if timestamp else ""
            self.chat_display.insert(tk.END, f"You{ts_str}\n", ("self_header", "own_header"))
            self.chat_display.insert(tk.END, f"{message}\n\n", ("self_msg", "own_msg"))
        else:
            ts_str = f" • {timestamp}" if timestamp else ""
            self.chat_display.insert(tk.END, f"{sender}{ts_str}\n", ("other_header",))
            self.chat_display.insert(tk.END, f"{message}\n\n", ("other_msg",))

        self._render_typing_indicator_line()

        self.chat_display.configure(state="disabled")
        self.chat_display.see(tk.END)

    def clear_chat(self) -> None:
        """Clears all text from the chat display (thread-safe)."""
        def _clear():
            if not self.winfo_exists():
                return
            if hasattr(self, "_active_typers"):
                self._active_typers.clear()
            self.chat_display.configure(state="normal")
            self.chat_display.delete("1.0", tk.END)
            self.chat_display.configure(state="disabled")

        self._run_on_ui_thread(_clear)

    # =========================================================================
    # AI Conversation Summary Handlers (B1)
    # =========================================================================

    def request_ai_summary(self) -> None:
        """Transmits AI_SUMMARY_REQ for the current room and displays loading feedback (B1)."""
        if getattr(self, "_is_requesting_summary", False):
            return

        self._is_requesting_summary = True
        if hasattr(self, "ai_summary_button") and self.ai_summary_button.winfo_exists():
            self.ai_summary_button.configure(text="⏳ Summarizing...", state="disabled")

        ts = get_current_timestamp()
        self.chat_display.configure(state="normal")
        for tag_name in ("ai_summary_status", "typing_indicator"):
            ranges = self.chat_display.tag_ranges(tag_name)
            if ranges:
                self.chat_display.delete(ranges[0], ranges[1])
        self.chat_display.insert(
            tk.END,
            f"[{ts}] ✨ Generating AI conversation summary...\n\n",
            ("ai_summary_status",),
        )
        self._render_typing_indicator_line()
        self.chat_display.configure(state="disabled")
        self.chat_display.see(tk.END)

        if self._summary_timeout_job:
            try:
                self.after_cancel(self._summary_timeout_job)
            except Exception:
                pass
        self._summary_timeout_job = self.after(15000, self.clear_ai_summary_loading)

        if self.network_client:
            if hasattr(self.network_client, "send_ai_summary_request"):
                self.network_client.send_ai_summary_request(self.room_type, self.target_name)
            elif hasattr(self.network_client, "send_packet"):
                self.network_client.send_packet(
                    MSG_AI_SUMMARY_REQ,
                    {"room_type": self.room_type, "target": self.target_name},
                )

    def clear_ai_summary_loading(self) -> None:
        """Clears the temporary AI summary loading status and re-enables the button (B1)."""
        def _clear_loading():
            if not self.winfo_exists():
                return
            self._is_requesting_summary = False
            if self._summary_timeout_job:
                try:
                    self.after_cancel(self._summary_timeout_job)
                except Exception:
                    pass
                self._summary_timeout_job = None

            if hasattr(self, "ai_summary_button") and self.ai_summary_button.winfo_exists():
                self.ai_summary_button.configure(text="✨ AI Summary", state="normal")

            self.chat_display.configure(state="normal")
            ranges = self.chat_display.tag_ranges("ai_summary_status")
            if ranges:
                self.chat_display.delete(ranges[0], ranges[1])
            self.chat_display.configure(state="disabled")

        self._run_on_ui_thread(_clear_loading)

    def display_ai_summary(
        self,
        summary: str,
        requested_by: str = "",
        timestamp: str = "",
    ) -> None:
        """Renders an incoming AI conversation summary inside the chat stream (B1)."""
        def _render_summary():
            if not self.winfo_exists():
                return

            self._is_requesting_summary = False
            if self._summary_timeout_job:
                try:
                    self.after_cancel(self._summary_timeout_job)
                except Exception:
                    pass
                self._summary_timeout_job = None

            if hasattr(self, "ai_summary_button") and self.ai_summary_button.winfo_exists():
                self.ai_summary_button.configure(text="✨ AI Summary", state="normal")

            ts = timestamp if timestamp else get_current_timestamp()
            requester_label = (
                "You"
                if requested_by and requested_by.lower() == self.own_username.lower()
                else (requested_by or "Participant")
            )

            self.chat_display.configure(state="normal")
            for tag_name in ("ai_summary_status", "typing_indicator"):
                ranges = self.chat_display.tag_ranges(tag_name)
                if ranges:
                    self.chat_display.delete(ranges[0], ranges[1])

            header_line = f"✨ AI Chat Summary (requested by {requester_label}) • {ts}\n"
            body_line = f"{summary.strip()}\n\n"

            self.chat_display.insert(tk.END, header_line, ("ai_summary_header",))
            self.chat_display.insert(tk.END, body_line, ("ai_summary_body",))

            self._render_typing_indicator_line()

            self.chat_display.configure(state="disabled")
            self.chat_display.see(tk.END)

        self._run_on_ui_thread(_render_summary)

    # =========================================================================
    # Multi-User Typing Indicator Handlers (B3)
    # =========================================================================

    def _on_key_press(self, event: Optional[tk.Event] = None) -> None:
        """Sends is_typing=True on keypress and sets a 3-second auto-stop timer (B3)."""
        if event and event.keysym in ("Return", "Tab", "Escape"):
            return

        if not self._is_typing_active and self.network_client:
            self._is_typing_active = True
            if hasattr(self.network_client, "send_typing"):
                self.network_client.send_typing(self.room_type, self.target_name, True)
            elif hasattr(self.network_client, "send_packet"):
                self.network_client.send_packet(MSG_TYPING, {
                    "room_type": self.room_type,
                    "target": self.target_name,
                    "from": self.own_username,
                    "sender": self.own_username,
                    "is_typing": True,
                })

        if self._typing_timer:
            try:
                self.after_cancel(self._typing_timer)
            except Exception:
                pass
        self._typing_timer = self.after(3000, self._stop_typing_status)

    def _stop_typing_status(self) -> None:
        """Notifies server that typing has stopped and cancels pending timer (B3)."""
        if self._typing_timer:
            try:
                self.after_cancel(self._typing_timer)
            except Exception:
                pass
            self._typing_timer = None

        if getattr(self, "_is_typing_active", False) and self.network_client:
            self._is_typing_active = False
            if hasattr(self.network_client, "send_typing"):
                self.network_client.send_typing(self.room_type, self.target_name, False)
            elif hasattr(self.network_client, "send_packet"):
                self.network_client.send_packet(MSG_TYPING, {
                    "room_type": self.room_type,
                    "target": self.target_name,
                    "from": self.own_username,
                    "sender": self.own_username,
                    "is_typing": False,
                })

    def _render_typing_indicator_line(self) -> None:
        """Formats and renders typing indicator text based on all active typing users (B3)."""
        ranges = self.chat_display.tag_ranges("typing_indicator")
        if ranges:
            self.chat_display.delete(ranges[0], ranges[1])

        if hasattr(self, "_active_typers") and self._active_typers:
            typers_list = sorted(list(self._active_typers))
            count = len(typers_list)

            if count == 1:
                text_str = f"✍ {typers_list[0]} is typing..."
            elif count == 2:
                text_str = f"✍ {typers_list[0]} and {typers_list[1]} are typing..."
            elif count == 3:
                text_str = f"✍ {typers_list[0]}, {typers_list[1]}, and {typers_list[2]} are typing..."
            else:
                text_str = f"✍ {typers_list[0]}, {typers_list[1]}, and {count - 2} others are typing..."

            self.chat_display.insert(tk.END, f"{text_str}\n\n", ("typing_indicator",))

    def set_typing_status(self, sender: str, is_typing: bool) -> None:
        """Tracks multiple typing users by username and updates group typing indicator (B3)."""
        def _update():
            if not self.winfo_exists():
                return

            if not hasattr(self, "_active_typers"):
                self._active_typers = set()

            if sender.lower() == self.own_username.lower() or sender == "You":
                return

            if is_typing:
                self._active_typers.add(sender)
            else:
                self._active_typers.discard(sender)

            self.chat_display.configure(state="normal")
            self._render_typing_indicator_line()
            self.chat_display.configure(state="disabled")
            self.chat_display.see(tk.END)

        self._run_on_ui_thread(_update)

    # =========================================================================
    # Voice Message Handlers & Replay (B4)
    # =========================================================================

    def _toggle_voice_recording(self) -> None:
        """Toggles push-to-talk voice recording on/off (B4)."""
        if self._is_recording_voice:
            self._stop_voice_recording()
        else:
            self._start_voice_recording()

    def _start_voice_recording(self) -> None:
        """Starts recording audio clip and sets 30-second auto-stop cap (B4)."""
        try:
            import sounddevice as sd
        except ImportError:
            self.display_message("System", "⚠ Please install sounddevice: pip install sounddevice numpy scipy", is_system=True)
            return

        self._is_recording_voice = True
        self._voice_start_time = time.time()
        self.voice_button.configure(text="⏹ Stop & Send")

        self._voice_auto_stop_timer = self.after(30000, self._stop_voice_recording)

        ts = get_current_timestamp()
        self.chat_display.configure(state="normal")
        ranges = self.chat_display.tag_ranges("recording_status")
        if ranges:
            self.chat_display.delete(ranges[0], ranges[1])
        self.chat_display.insert(tk.END, f"[{ts}] 🎙 Recording voice message (max 30s)...\n\n", ("recording_status",))
        self.chat_display.configure(state="disabled")
        self.chat_display.see(tk.END)

        self._temp_voice_file = os.path.join(tempfile.gettempdir(), f"voice_{int(time.time())}.wav")
        self._audio_frames = []

        def callback(indata, frames, time_info, status):
            if self._is_recording_voice:
                self._audio_frames.append(indata.copy())

        try:
            self._stream = sd.InputStream(samplerate=16000, channels=1, callback=callback)
            self._stream.start()
        except Exception as e:
            self._is_recording_voice = False
            self.voice_button.configure(text="🎤 Record Voice")
            if hasattr(self, "_voice_auto_stop_timer") and self._voice_auto_stop_timer:
                try:
                    self.after_cancel(self._voice_auto_stop_timer)
                except Exception:
                    pass
                self._voice_auto_stop_timer = None

            self.chat_display.configure(state="normal")
            ranges = self.chat_display.tag_ranges("recording_status")
            if ranges:
                self.chat_display.delete(ranges[0], ranges[1])
            self.chat_display.configure(state="disabled")
            self.display_message("System", f"⚠ Voice recording failed: {e}", is_system=True)

    def _stop_voice_recording(self) -> None:
        """Stops recording, checks 5MB payload limit, encodes WAV, and sends to server (B4)."""
        if not getattr(self, "_is_recording_voice", False):
            return

        self._is_recording_voice = False
        self.voice_button.configure(text="🎤 Record Voice")

        if hasattr(self, "_voice_auto_stop_timer") and self._voice_auto_stop_timer:
            try:
                self.after_cancel(self._voice_auto_stop_timer)
            except Exception:
                pass
            self._voice_auto_stop_timer = None

        duration = round(time.time() - getattr(self, "_voice_start_time", time.time()), 1)

        if hasattr(self, "_stream") and self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        self.chat_display.configure(state="normal")
        ranges = self.chat_display.tag_ranges("recording_status")
        if ranges:
            self.chat_display.delete(ranges[0], ranges[1])
        self.chat_display.configure(state="disabled")

        if not hasattr(self, "_audio_frames") or not self._audio_frames:
            self.display_message("System", "⚠ Voice recording failed or audio device not found.", is_system=True)
            return

        try:
            import numpy as np
            from scipy.io import wavfile

            audio_data = np.concatenate(self._audio_frames, axis=0)
            wavfile.write(self._temp_voice_file, 16000, audio_data)

            with open(self._temp_voice_file, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode("utf-8")

            if len(audio_b64.encode("utf-8")) > 4.5 * 1024 * 1024:
                self.show_error("Voice recording too large (exceeds server limit of 5 MB). Please record a shorter message.")
                return

            ts = get_current_timestamp()
            self.append_voice_message(
                sender=self.own_username,
                audio_b64=audio_b64,
                duration=duration,
                timestamp=ts,
            )

            if self.network_client:
                if hasattr(self.network_client, "send_voice_message"):
                    self.network_client.send_voice_message(self.room_type, self.target_name, audio_b64, duration)
                elif hasattr(self.network_client, "send_packet"):
                    self.network_client.send_packet(MSG_VOICE_MSG, {
                        "room_type": self.room_type,
                        "target": self.target_name,
                        "to": self.target_name,
                        "group": self.target_name,
                        "from": self.own_username,
                        "sender": self.own_username,
                        "audio_b64": audio_b64,
                        "duration": duration,
                    })
        except Exception as err:
            self.show_error(f"Failed to process voice message: {err}")

    def _play_audio_b64(self, audio_b64: str) -> None:
        """Decodes Base64 audio data and plays it natively via OS sound player (B4)."""
        try:
            wav_bytes = base64.b64decode(audio_b64)
            temp_play_file = os.path.join(tempfile.gettempdir(), f"play_{int(time.time() * 1000)}.wav")
            with open(temp_play_file, "wb") as f:
                f.write(wav_bytes)

            if sys.platform == "darwin":  # macOS
                subprocess.Popen(["afplay", temp_play_file])
            elif sys.platform.startswith("win"):  # Windows
                try:
                    import winsound
                    winsound.PlaySound(temp_play_file, winsound.SND_FILENAME | winsound.SND_ASYNC)
                except Exception:
                    subprocess.Popen(["powershell", "-c", f"(New-Object Media.SoundPlayer '{temp_play_file}').PlaySync()"])
            else:  # Linux
                subprocess.Popen(["aplay", temp_play_file])
        except Exception as err:
            self.show_error(f"Playback failed: {err}")

    def append_voice_message(
        self,
        sender: str,
        audio_b64: str,
        duration: float,
        timestamp: str = "",
        autoplay: bool = True,
    ) -> None:
        """Embeds a replayable voice clip formatted and aligned like standard chat text (B4)."""
        def _append():
            if not self.winfo_exists():
                return

            ts = timestamp if timestamp else get_current_timestamp()
            is_self = (sender == self.own_username or sender.lower() == self.own_username.lower() or sender == "You")

            if autoplay and is_self and self.on_voice_sent_callback:
                try:
                    self.on_voice_sent_callback(
                        self.room_type,
                        self.target_name,
                        self.own_username,
                        audio_b64,
                        duration,
                        ts,
                    )
                except Exception:
                    pass

            if hasattr(self, "_active_typers"):
                self._active_typers.discard(sender)

            self.chat_display.configure(state="normal")

            for tag_name in ("typing_indicator", "recording_status"):
                ranges = self.chat_display.tag_ranges(tag_name)
                if ranges:
                    self.chat_display.delete(ranges[0], ranges[1])

            ts_str = f" • {ts}" if ts else ""
            if is_self:
                self.chat_display.insert(tk.END, f"You{ts_str}\n", ("self_header", "own_header"))
            else:
                self.chat_display.insert(tk.END, f"{sender}{ts_str}\n", ("other_header",))

            start_idx = self.chat_display.index("end-1c")

            play_btn = tk.Button(
                self.chat_display,
                text=f"🎵 Voice Clip ({duration:.1f}s) ▶",
                font=("Segoe UI", 9, "bold"),
                bg="#1976D2" if is_self else "#E0E0E0",
                fg="#FFFFFF" if is_self else "#212121",
                activebackground="#1565C0" if is_self else "#D6D6D6",
                activeforeground="#FFFFFF" if is_self else "#000000",
                relief="flat",
                bd=0,
                padx=12,
                pady=5,
                cursor="hand2",
                command=lambda b64=audio_b64: self._play_audio_b64(b64),
            )

            if not hasattr(self, "_voice_buttons"):
                self._voice_buttons = []
            self._voice_buttons.append(play_btn)

            self.chat_display.window_create(tk.END, window=play_btn)
            self.chat_display.insert(tk.END, "\n\n")
            end_idx = self.chat_display.index("end-1c")

            tags_to_apply = ("self_msg", "own_msg") if is_self else ("other_msg", "other")
            for tag in tags_to_apply:
                self.chat_display.tag_add(tag, start_idx, end_idx)

            self._render_typing_indicator_line()

            self.chat_display.configure(state="disabled")
            self.chat_display.see(tk.END)

            if autoplay and not is_self:
                self._play_audio_b64(audio_b64)

        self._run_on_ui_thread(_append)

    # =========================================================================
    # Action Handling & Message Sending (R6)
    # =========================================================================

    def _on_return(self, event: Optional[tk.Event] = None) -> str:
        """Handles <Return> key event to trigger message transmission seamlessly (R6)."""
        self.send_message()
        return "break"

    def send_message(self) -> None:
        """Reads input text, transmits message, and clears input entry (R6)."""
        text = self.message_entry.get().strip()
        if not text:
            return

        if self._typing_timer:
            try:
                self.after_cancel(self._typing_timer)
            except Exception:
                pass
        self._stop_typing_status()

        self.message_entry.delete(0, tk.END)

        handled = False
        if self.on_send_message_callback:
            try:
                res = self.on_send_message_callback(self.target_name, text)
            except TypeError:
                res = self.on_send_message_callback(text)  # type: ignore
            if res is not False:
                handled = True

        if not handled and self.network_client:
            if self.room_type == ROOM_PRIVATE:
                if hasattr(self.network_client, "send_private_message"):
                    self.network_client.send_private_message(self.target_name, text)
                elif hasattr(self.network_client, "send_packet"):
                    self.network_client.send_packet(MSG_PRIVATE, {"to": self.target_name, "text": text})
            else:
                if hasattr(self.network_client, "send_group_message"):
                    self.network_client.send_group_message(self.target_name, text)
                elif hasattr(self.network_client, "send_packet"):
                    self.network_client.send_packet(MSG_GROUP, {"group": self.target_name, "text": text})
        elif not handled and not self.network_client:
            self.display_message(self.own_username, text, is_self=True)

    def on_send(self) -> None:
        """Alias for send_message."""
        self.send_message()

    # =========================================================================
    # Window Close Protocol & Cleanup (R5)
    # =========================================================================

    def destroy(self) -> None:
        """Cleanly stops voice stream, cancels scheduled timers, and notifies server if typing (B1, B3, B4)."""
        if getattr(self, "_is_typing_active", False):
            self._stop_typing_status()

        if getattr(self, "_is_recording_voice", False):
            self._is_recording_voice = False
            if hasattr(self, "_stream") and self._stream:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None

        for job_attr in ("_typing_timer", "_focus_job", "_poll_job", "_voice_auto_stop_timer", "_summary_timeout_job"):
            job = getattr(self, job_attr, None)
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
                setattr(self, job_attr, None)

        super().destroy()

    def _on_window_close(self) -> None:
        """Handles WM_DELETE_WINDOW protocol and invokes cleanup callback (R5)."""
        if self._poll_job:
            try:
                self.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None

        if self.on_close_callback:
            try:
                self.on_close_callback(self.room_type, self.target_name)
            except TypeError:
                try:
                    self.on_close_callback(self.target_name)
                except TypeError:
                    self.on_close_callback()

        self.destroy()
