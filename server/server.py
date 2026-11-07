"""
Module: server/server.py
Purpose: Main TCP Server Entry Point & Connection Acceptor
Mapped Requirements:
  - R1 (System Architecture): Runs on a host computer, binds to a LAN-accessible IP/Port
    so at least two physical client computers can connect over TCP.
  - R2 (Socket Programming Only): Uses Python's standard `socket` module (`AF_INET`, `SOCK_STREAM`).
"""

import argparse
import logging
import signal
import socket
import sys
import threading
from typing import Optional

from common.protocol import DEFAULT_HOST, DEFAULT_PORT
from server.client_handler import handle_client
from server.state import ServerState

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(threadName)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("server")


def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't actually send packets, just finds routing interface
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def start_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, state: Optional[ServerState] = None) -> None:
    if state is None:
        state = ServerState()

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Allow immediate reuse of the port upon server restart
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_sock.bind((host, port))
        server_sock.listen(10)
    except OSError as err:
        logger.error(f"Failed to bind/listen on {host}:{port}: {err}")
        server_sock.close()
        sys.exit(1)

    lan_ip = get_local_ip()
    logger.info("=" * 60)
    logger.info("🚀 Simple Chat TCP Server Started (R1, R2)")
    logger.info(f"   Bind Address:    {host}:{port}")
    logger.info(f"   Local LAN IP:    {lan_ip}:{port}")
    logger.info("   Protocol:        TCP / Newline-Delimited UTF-8 JSON")
    logger.info("   Ready to accept client connections...")
    logger.info("=" * 60)

    # Graceful shutdown on Docker / Linux SIGTERM
    try:
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    except (ValueError, AttributeError):
        pass

    try:
        while True:
            client_sock, client_addr = server_sock.accept()
            # Enable TCP Keepalive to detect dead/silent client drops on VPS (Must Fix 1)
            try:
                client_sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            except OSError:
                pass

            worker_thread = threading.Thread(
                target=handle_client,
                args=(client_sock, client_addr, state),
                name=f"Worker-{client_addr[0]}:{client_addr[1]}",
                daemon=True,
            )
            worker_thread.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("\nServer shutdown requested. Cleaning up sockets...")
    finally:
        try:
            server_sock.close()
        except OSError:
            pass
        logger.info("Server socket closed. Goodbye!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Computer Networks Chat TCP Server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host/IP to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind (default: 5000)")
    args = parser.parse_args()

    start_server(args.host, args.port)
