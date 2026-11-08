# Project Overview & Single Source of Truth

**Document Status:** Active
**Last Synchronized:** 2026-11-08
**Current Sprint / Phase:** Bonus B1 (AI Summary) & Cloud VPS Hardening Completed (47/47 Tests Passing)

---

## 1. Project Synopsis & Background
- **What is this project?** A multi-client networked chat application built in Python using raw TCP Socket Programming and a Tkinter GUI.
- **Origin & Context:** Term Project for Computer Networks (`Simple Chat Application`). Designed to demonstrate socket programming across at least two physical client computers communicating through a central server (hosted on LAN or a Cloud VPS).
- **Scope:** Covers **Part 1 (System Architecture Design: R1–R2)**, **Part 2 (Fundamental Implementation: R3–R11)**, and **Part 3 (Bonus / Special Features: B1–B4)**.

---

## 2. Objectives & Requirements Mapping (`R1`–`R11` & `B1`–`B4`)

### Part 1: System Architecture Design (1.5 points)
- **R1 (1.0):** Present system architecture with at least two clients on different physical computers and one server (on one of those computers, a third machine, or a Cloud VPS). Explain protocols used (TCP/IP + custom JSON application framing), why selected (reliable, ordered, connection-oriented delivery), and how used.
- **R2 (0.5):** Chat messages between server and clients must be implemented using **Socket Programming only** (`socket` module).

### Part 2: Fundamental Implementation (7.0 points)
- **R3 (0.5):** Each client must have a **unique name** (validated by server upon login/registration).
- **R4 (0.5):** Each client can see a **list of names of all clients** currently connected to the server, **including its own name**.
- **R5 (0.5):** Each chat between clients (both **Private** and **Group** message) must have **its own chat room** (implemented as dedicated `tk.Toplevel` windows per peer/group).
- **R6 (0.5):** Each chat room (both **Private** and **Group** message) must include a **chat box** for sending text messages and a **chat window** for displaying sent messages and new incoming messages.
- **R7 (1.0) [Private]:** Each client can send a direct text message to any client in the list. **Only the sender and receiver** can see the messages.
- **R8 (1.0) [Group]:** Each client can create chat group(s), which **initially includes only themselves** as a member.
- **R9 (1.0) [Group]:** Each client can see a **list of all existing chat groups (with the member list)** created by any client.
- **R10 (1.0) [Group]:** Clients can choose to **join a group chat only by themselves**; they are **not** added automatically by the group creator.
- **R11 (1.0) [Group]:** Each client can send a text message to a group they have joined. **Only the members of that chat group** can see the messages.

### Part 3: Bonus / Special Features (1.5 points)
- **B1 [AI Summary]:** Server stores per-room chat history in memory and summarizes the conversation on request (`AI_SUMMARY_REQ`) using Google Gemini REST API (`server/ai_service.py`), broadcasting the summary (`AI_SUMMARY_RES`) to all participants in that room, with offline heuristic fallback when API key is unset.
- **B2 [Cloud VPS Deployment]:** Server binds to `0.0.0.0` on a Cloud VPS with an open TCP firewall port so clients on any network can connect via the VPS Public IP.
- **B3 [Typing Indicator]:** Discord-style real-time `"<user> is typing..."` status bar (`TYPING`) in both Private and Group chat rooms, with automatic debounce/timeout after 3 seconds of inactivity or upon sending a message.
- **B4 [Voice Message]:** Push-to-talk / recorded `.wav` audio clips (`client/audio.py`) encoded in Base64 (`VOICE_MSG`) and sent over the same TCP JSON connection for playback inside Private and Group chat rooms.

---

## 3. System Architecture & Tech Stack
- **Architecture Overview:** Centralized Client-Server star topology over TCP/IP (LAN or Cloud VPS Public IP).
  - **Transport Layer:** TCP (`socket.AF_INET`, `socket.SOCK_STREAM`) for reliable, ordered byte-stream delivery without packet loss.
  - **Application Protocol Layer:** Newline-delimited (`\n`) UTF-8 JSON messages using a standardized 3-key Envelope (`type`, `timestamp`, `payload`).
- **Frontend (Client GUI):** Python `tkinter` & `tkinter.ttk`
  - **Login Window (`client/gui_login.py`):** Server IP (LAN or Cloud VPS Public IP), Port, and unique Username input.
  - **Main Lobby (`client/gui_lobby.py`):** Displays online clients (`R4`) and all groups with member lists (`R9`), plus controls to open Private Chats (`R5`), Create Group (`R8`), and Join Group (`R10`).
  - **Chat Room Window (`client/gui_chatroom.py`):** Separate `tk.Toplevel` window per Private peer or joined Group (`R5`), with message history display, input box (`R6`), Typing Indicator status bar (`B3`), and Voice Message recorder/player (`B4`).
  - **Audio Helper (`client/audio.py`):** Records/plays short `.wav` voice clips and converts between raw audio bytes and Base64 strings (`B4`).
- **Backend (Server):** Python `socket` + `threading`
  - One main listening thread accepting connections (`server/server.py`).
  - Thread-safe state store protected by `threading.Lock` (`server/state.py`), maintaining active clients, groups, and bounded per-room message history for AI summarization.
  - Dedicated worker thread per connected client (`server/client_handler.py`).
  - Modular Handlers (`server/handlers/`):
    - `register.py`: Client registration (`R3`), client directory broadcast (`R4`), & initial existing group list push (`R9`).
    - `private_msg.py`: 1-on-1 private messaging (`R7`) & history recording (`B1`).
    - `group.py`: Group creation (`R8`), directory broadcast (`R9`), self-join (`R10`), group multicast (`R11`), & history recording (`B1`).
    - `typing.py`: Real-time typing indicator relay for private & group chats (`B3`).
    - `audio.py`: Push-to-talk Base64 voice message relay for private & group chats (`B4`).
    - `ai_summary.py`: Asynchronous AI chat summarization handler for private & group rooms (`B1`).
  - Server-side AI Summarizer (`server/ai_service.py`) calling Gemini REST API via `urllib.request` with `.env` loader (`load_env_file`) and offline fallback.
- **Directory Structure:**
  ```text
  CompNetwork/
  ├── GEMINI.md                  # Workspace rules & directives
  ├── OVERVIEW_PROJECT.md        # Single Source of Truth architecture & specs
  ├── SESSION_STATE.md           # Session progress & handoff state
  ├── README.md                  # Server setup guide (Docker Desktop, Cloud VPS & Python 3)
  ├── JsonFormat.md              # Full wire protocol reference
  ├── Dockerfile                 # Server-only container image (python:3.12-slim, port 5000) (B2)
  ├── docker-compose.yml         # One-command server deployment & auto-restart config (B2)
  ├── .dockerignore              # Excludes client GUI, tests, and docs from server image (B2)
  ├── .env.example               # Template environment configuration (GEMINI_API_KEY)
  ├── common/
  │   ├── __init__.py
  │   └── protocol.py            # Shared JSON message types, schemas & TCP framing specs (R1, R2, B1, B3, B4)
  ├── server/
  │   ├── __init__.py
  │   ├── server.py              # TCP listener entry point & thread spawner (R1, R2, B2)
  │   ├── state.py               # Thread-safe registry of clients, groups & room chat history (R3, R4, R8–R10, B1)
  │   ├── client_handler.py      # Per-client packet router & broadcast logic (R2–R11, B1, B3, B4)
  │   ├── handlers/              # Modular action handlers package
  │   │   ├── __init__.py        # Exported handler functions
  │   │   ├── register.py        # handle_register & broadcast_client_list (R3, R4)
  │   │   ├── private_msg.py     # handle_private_msg (R7)
  │   │   ├── group.py           # handle_create_group, handle_join_group, handle_group_msg (R8-R11)
  │   │   ├── typing.py          # handle_typing real-time typing indicator relay (B3)
  │   │   ├── audio.py           # handle_voice_msg push-to-talk audio relay (B4)
  │   │   └── ai_summary.py      # handle_ai_summary async AI summarizer (B1)
  │   └── ai_service.py          # Zero-dependency Gemini API & offline heuristic summarizer (B1)
  ├── client/
  │   ├── __init__.py
  │   ├── main.py                # Client application entry point & UI controller
  │   ├── network.py             # Client TCP socket thread & thread-safe UI queue (R2, B1, B3, B4)
  │   ├── audio.py               # WAV voice clip recording, playback & Base64 encoding/decoding (B4)
  │   ├── gui_login.py           # Login dialog for Server IP (LAN/VPS), port & unique username (R1, R3, B2)
  │   ├── gui_lobby.py           # Lobby window for online client directory & group directory (R4, R8-R10)
  │   └── gui_chatroom.py        # Dedicated chat room window per peer/group (R5, R6, B3, B4)
  └── tests/
      ├── test_socket_r2.py
      ├── test_handler_register.py
      ├── test_messaging.py
      ├── test_client_requirements.py
      ├── test_typing.py
      ├── test_audio.py
      └── test_ai_summary.py
  ```
