"""
Multithreaded TCP Server for IRCTC-Style Train Reservation System
Listens on port 5000 (configurable), accepts concurrent client connections,
spawns dedicated worker threads, and provides graceful shutdown mechanics.
"""

import os
import socket
import threading
from typing import List, Optional

from client_handler import ClientHandler
from logger import logger


class TCPServer:
    """
    Multithreaded TCP socket listener and connection coordinator.
    """

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, timeout: Optional[float] = None):
        self.host = host if host is not None else os.getenv("TCP_HOST", "0.0.0.0")
        self.port = port if port is not None else int(os.getenv("TCP_PORT", "5000"))
        self.client_timeout = timeout if timeout is not None else float(os.getenv("TCP_TIMEOUT", "60.0"))

        self._server_sock: Optional[socket.socket] = None
        self._running = False
        self._active_clients: List[ClientHandler] = []
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Binds TCP socket, starts listening, and launches the acceptance loop."""
        with self._lock:
            if self._running:
                return

            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((self.host, self.port))
                sock.listen(50)
                self._server_sock = sock
                self._running = True

                self._thread = threading.Thread(target=self._accept_loop, daemon=True, name="TCP-Listener")
                self._thread.start()
                logger.info("Multithreaded TCP Reservation Server listening on %s:%d", self.host, self.port)
            except Exception as e:
                logger.error("Failed to start TCP Server on %s:%d: %s", self.host, self.port, str(e))
                self._running = False
                if self._server_sock:
                    try:
                        self._server_sock.close()
                    except Exception:
                        pass
                    self._server_sock = None
                raise

    def _accept_loop(self) -> None:
        """Accepts incoming TCP client sockets and spawns ClientHandler threads."""
        while self._running:
            try:
                client_sock, client_addr = self._server_sock.accept()
                handler = ClientHandler(client_sock, client_addr, timeout=self.client_timeout)

                with self._lock:
                    # Purge dead threads
                    self._active_clients = [c for c in self._active_clients if c.is_alive()]
                    self._active_clients.append(handler)

                handler.start()
            except socket.error:
                # Socket closed during shutdown
                break
            except Exception as e:
                if self._running:
                    logger.error("Error accepting TCP connection: %s", str(e))
                break

    def stop(self) -> None:
        """Gracefully terminates listener and closes all active client sockets."""
        with self._lock:
            if not self._running:
                return
            self._running = False

            if self._server_sock:
                try:
                    self._server_sock.close()
                except Exception:
                    pass
                self._server_sock = None

            # Close all active client connections
            for client in self._active_clients:
                try:
                    client._cleanup()
                except Exception:
                    pass
            self._active_clients.clear()

            logger.info("TCP Reservation Server successfully stopped.")

    def get_active_client_count(self) -> int:
        """Returns the number of currently active client connections."""
        with self._lock:
            self._active_clients = [c for c in self._active_clients if c.is_alive()]
            return len(self._active_clients)
