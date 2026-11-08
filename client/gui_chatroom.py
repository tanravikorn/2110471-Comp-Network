"""
Module: client/gui_chatroom.py
Purpose: Reusable Tkinter Toplevel Chat Room Window UI Component for Requirements R5 and R6
Mapped Requirements:
  - R5 (Separate Chat Rooms): Dedicated chat room window (`tk.Toplevel`).
  - R6 (Chat Box & Chat Window): Read-only ScrolledText message display & Entry input box.
  - B3 (Typing Indicator): Real-time typing status rendered directly inside the chat history stream.
"""

from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import scrolledtext, ttk
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.protocol import (
    MSG_GROUP,
    MSG_PRIVATE,
    MSG_TYPING,
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
        **kwargs: Any,
    ) -> None:
        super().__init__(parent)

        if callable(network_client) and on_send_message_callback is None:
            on_send_message_callback = network_client
            network_client = None

        if "on_send_message_callback" in kwargs and on_send_message_callback is None:
            on_send_message_callback = kwargs["on_send_message_callback"]
        if "on_close_callback" in kwargs and on_close_callback is None:
            on_close_callback = kwargs["on_close_callback"]

        self.room_type = room_type
        self.target_name = target_name
        self.own_username = own_username
        self.network_client = network_client
        self.on_close_callback = on_close_callback
        self.on_send_message_callback = on_send_message_callback

        # Real-time typing status state (B3)
        self._typing_timer: Optional[str] = None
        self._is_typing_active: bool = False

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
        self.geometry("520x600")
        self.minsize(420, 460)

        # Handle window close protocol (WM_DELETE_WINDOW)
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # Build UI layout & tags (R6)
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
    # UI Layout & Widget Creation (R5, R6)
    # =========================================================================

    def _build_ui(self) -> None:
        """Constructs all GUI sub-components for R5 and R6."""
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

        # 3. Message Input Area (R6 Chat Box)
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

        self._focus_job: Optional[str] = self.after(50, self._focus_entry)

    def _focus_entry(self) -> None:
        """Helper to safely focus input entry if window still exists."""
        if self.winfo_exists():
            self.message_entry.focus_set()

    def _configure_tags(self) -> None:
        """Configures Tkinter text tags for formatting message styles (R6, B3)."""
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

        # Real-time Typing Indicator tag inside chat stream (B3)
        self.chat_display.tag_config(
            "typing_indicator",
            justify="left",
            foreground="#3182CE",
            font=("Segoe UI", 9, "italic"),
            lmargin1=12,
            lmargin2=12,
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
        """Renders recorded history into the chat widget (B1)."""
        def _render():
            if not self.winfo_exists():
                return
            self.chat_display.configure(state="normal")
            self.chat_display.delete("1.0", tk.END)
            for item in history:
                if not isinstance(item, dict):
                    continue
                sender = str(item.get("sender", "System")).strip() or "System"
                text = str(item.get("text", "")).strip()
                timestamp = str(item.get("timestamp", "")).strip()
                if not text:
                    continue

                is_self = sender.lower() == self.own_username.lower()
                if is_self:
                    ts_str = f" • {timestamp}" if timestamp else ""
                    self.chat_display.insert(tk.END, f"You{ts_str}\n", ("self_header", "own_header"))
                    self.chat_display.insert(tk.END, f"{text}\n\n", ("self_msg", "own_msg"))
                else:
                    ts_str = f" • {timestamp}" if timestamp else ""
                    self.chat_display.insert(tk.END, f"{sender}{ts_str}\n", ("other_header",))
                    self.chat_display.insert(tk.END, f"{text}\n\n", ("other_msg",))
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

        self.chat_display.configure(state="normal")

        # Clear any active typing indicator before inserting a new message
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

        self.chat_display.configure(state="disabled")
        self.chat_display.see(tk.END)

    def clear_chat(self) -> None:
        """Clears all text from the chat display (thread-safe)."""
        def _clear():
            if not self.winfo_exists():
                return
            self.chat_display.configure(state="normal")
            self.chat_display.delete("1.0", tk.END)
            self.chat_display.configure(state="disabled")

        self._run_on_ui_thread(_clear)

    # =========================================================================
    # Typing Indicator Handlers (B3)
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
                    "is_typing": True,
                })

        if self._typing_timer:
            self.after_cancel(self._typing_timer)
        self._typing_timer = self.after(3000, self._stop_typing_status)

    def _stop_typing_status(self) -> None:
        """Notifies server that typing has stopped after 3 seconds of inactivity (B3)."""
        if self._is_typing_active and self.network_client:
            self._is_typing_active = False
            if hasattr(self.network_client, "send_typing"):
                self.network_client.send_typing(self.room_type, self.target_name, False)
            elif hasattr(self.network_client, "send_packet"):
                self.network_client.send_packet(MSG_TYPING, {
                    "room_type": self.room_type,
                    "target": self.target_name,
                    "is_typing": False,
                })
        self._typing_timer = None

    def set_typing_status(self, sender: str, is_typing: bool) -> None:
        """Renders '✍ <user> is typing...' in the chat display on the next line after the latest message (B3)."""
        def _update():
            if not self.winfo_exists():
                return

            self.chat_display.configure(state="normal")

            # Remove existing typing indicator line if present
            ranges = self.chat_display.tag_ranges("typing_indicator")
            if ranges:
                self.chat_display.delete(ranges[0], ranges[1])

            if is_typing:
                self.chat_display.insert(tk.END, f"✍ {sender} is typing...\n\n", ("typing_indicator",))
                self.chat_display.see(tk.END)

            self.chat_display.configure(state="disabled")

        self._run_on_ui_thread(_update)

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

        # Cancel typing timer immediately upon send (B3)
        if self._typing_timer:
            self.after_cancel(self._typing_timer)
        self._stop_typing_status()

        # Clear input box (R6)
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
        """Cleanly cancels scheduled timers before destroying the window."""
        if hasattr(self, "_typing_timer") and self._typing_timer:
            try:
                self.after_cancel(self._typing_timer)
            except Exception:
                pass
            self._typing_timer = None

        if hasattr(self, "_focus_job") and self._focus_job:
            try:
                self.after_cancel(self._focus_job)
            except Exception:
                pass
            self._focus_job = None

        if self._poll_job:
            try:
                self.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None

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


# =============================================================================
# Standalone Mock & Preview Launcher (R5, R6)
# =============================================================================
if __name__ == "__main__":
    import time

    def _safe_print(*args: Any, **kwargs: Any) -> None:
        try:
            print(*args, **kwargs)
        except UnicodeEncodeError:
            enc = sys.stdout.encoding or "utf-8"
            clean_args = [str(a).encode(enc, errors="replace").decode(enc) for a in args]
            print(*clean_args, **kwargs)

    _safe_print("[ChatRoomWindow] Launching standalone preview with mock callbacks...")
    root = tk.Tk()
    root.withdraw()

    def mock_on_send(target: str, text: str) -> None:
        _safe_print(f"[MOCK SEND -> {target}] {text}")
        window.display_message(sender="CurrentUser", message=text, is_self=True)

        def _simulate_peer_reply():
            if window.winfo_exists():
                window.display_message(sender=target, message=f"Echo reply: '{text}' received!", is_self=False)

        window.after(1000, _simulate_peer_reply)

    def mock_on_close(room_type: str = "", target: str = "") -> None:
        _safe_print(f"[MOCK CLOSE] Chat window for {target} ({room_type}) closed.")
        root.destroy()

    window = ChatRoomWindow(
        parent=root,
        room_type=ROOM_GROUP,
        target_name="StudyGroup",
        own_username="CurrentUser",
        on_send_message_callback=mock_on_send,
        on_close_callback=mock_on_close,
    )
    window.set_participants(["CurrentUser", "Alice", "Bob"])

    window.display_message("System", "Welcome to StudyGroup chat room!", is_system=True)
    window.display_message("Alice", "Hello team! Is our R5/R6 chat window component ready?", timestamp="14:00:10")
    window.display_message("CurrentUser", "Yes! It has thread safety, auto-scroll, and text tags.", timestamp="14:00:45", is_self=True)
    window.display_message("Bob", "Awesome, testing message input and send button now.", timestamp="14:01:20")

    def background_thread_worker():
        time.sleep(2)
        window.display_message(
            sender="Alice",
            message="[Thread-Safe Message] Delivered safely from a background thread via after()!",
            is_self=False,
        )

    bg_thread = threading.Thread(target=background_thread_worker, daemon=True)
    bg_thread.start()

    root.mainloop()