"""
Module: client/gui_login.py
Purpose: Tkinter Login & Server Connection Dialog
Mapped Requirements:
  - R1 (System Architecture): Allows specifying the Server IP address and TCP Port so clients
    on separate physical computers can connect over LAN.
  - R3 (Unique Client Name): Prompts the user for a unique client name and displays an error
    if the server reports that the name is already taken by another connected client.
"""

# ==============================================================================
# TODO 1: Define `LoginWindow` Class (Tkinter Frame or Toplevel)
# ==============================================================================
# - UI Widgets to create:
#     1. Server IP Entry (`tk.Entry`, default e.g. `"127.0.0.1"` or LAN IP)
#     2. Server Port Entry (`tk.Entry`, default `DEFAULT_PORT`)
#     3. Unique Username Entry (`tk.Entry`) (R3)
#     4. Status / Error Label (`tk.Label` for showing connection or duplicate-name errors)
#     5. "Connect & Join" Button (`tk.Button`)

# ==============================================================================
# TODO 2: Implement Connection & Registration Handshake (R1, R3)
# ==============================================================================
# - On clicking "Connect & Join":
#     1. Validate that Server IP, Port, and Username are non-empty.
#     2. If not yet connected to the server socket, call `network_client.connect(ip, port)`.
#     3. Send `network_client.send_register(username)`.
#     4. Poll `network_client.incoming_queue` (via `after()`) for `MSG_REGISTER_ACK`:
#          - If `success == True`: invoke `on_login_success(username)` callback to open `LobbyWindow`.
#          - If `success == False`: display the rejection message (e.g., "Username already taken")
#            so the user can enter a different unique name (R3).
