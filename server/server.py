"""
Module: server/server.py
Purpose: Main TCP Server Entry Point & Connection Acceptor
Mapped Requirements:
  - R1 (System Architecture): Runs on a host computer, binds to a LAN-accessible IP/Port
    so at least two physical client computers can connect over TCP.
  - R2 (Socket Programming Only): Uses Python's standard `socket` module (`AF_INET`, `SOCK_STREAM`).
"""

# ==============================================================================
# TODO 1: Import Standard Modules & Local Dependencies
# ==============================================================================
# - Import `socket`, `threading`, `sys`
# - Import `DEFAULT_HOST`, `DEFAULT_PORT` from `common.protocol`
# - Import `ServerState` from `server.state`
# - Import `handle_client` from `server.client_handler`

# ==============================================================================
# TODO 2: Implement `start_server(host: str, port: int)`
# ==============================================================================
# 1. Instantiate a single shared `ServerState()` object to hold connected clients and groups.
# 2. Create a TCP socket: `server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)`.
# 3. Set socket option `SO_REUSEADDR` so the server port can be restarted immediately.
# 4. Bind `server_sock` to `(host, port)` and call `server_sock.listen()`.
# 5. Print the server's LAN IP address and listening port to the console so client PCs
#    know which IP/Port to connect to during the R1 demonstration.
# 6. Enter the main `while True:` accept loop:
#      - Accept incoming connection: `client_sock, client_addr = server_sock.accept()`
#      - Spawn a daemon `threading.Thread` targeting `handle_client(client_sock, client_addr, state)`
#      - Start the thread.
# 7. Handle `KeyboardInterrupt` gracefully by closing client sockets and `server_sock`.

# ==============================================================================
# TODO 3: Implement CLI Entry Point (`if __name__ == "__main__":`)
# ==============================================================================
# - Allow optional CLI arguments for host and port (defaulting to `0.0.0.0` and `DEFAULT_PORT`).
# - Call `start_server(host, port)`.
