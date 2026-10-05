"""
UDP Notification Server for IRCTC-Style Train Reservation System
Provides lightweight, asynchronous UDP datagram broadcasting for
live train status updates, delay alerts, platform changes, and booking notices.
"""

import json
import os
import socket
import threading
import time
from typing import Any, Dict, Optional

from logger import logger


class UDPServer:
    """
    Manages asynchronous UDP broadcast transmissions to listening client terminals.
    """

    def __init__(
        self,
        bind_host: Optional[str] = None,
        port: Optional[int] = None,
        target_broadcast_port: Optional[int] = None
    ):
        self.bind_host = bind_host if bind_host is not None else os.getenv("UDP_HOST", "0.0.0.0")
        self.port = port if port is not None else int(os.getenv("UDP_PORT", "6000"))
        self.broadcast_port = target_broadcast_port if target_broadcast_port is not None else int(os.getenv("UDP_BROADCAST_PORT", "9999"))
        self._sock: Optional[socket.socket] = None
        self._running: bool = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Initializes the UDP socket with broadcast permissions."""
        with self._lock:
            if self._running:
                return

            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                except Exception:
                    pass

                sock.bind((self.bind_host, self.port))
                self._sock = sock
                self._running = True
                logger.info("UDP Notification Service initialized on %s:%d (Target Client Port: %d)", self.bind_host, self.port, self.broadcast_port)
            except Exception as e:
                logger.error("Failed to bind UDP socket: %s", str(e))
                self._sock = None
                self._running = False

    def stop(self) -> None:
        """Closes the UDP socket."""
        with self._lock:
            self._running = False
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
            logger.info("UDP Notification Service stopped.")

    def broadcast_announcement(
        self,
        message: str,
        alert_type: str = "INFO",
        extra_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Emits a structured JSON notification datagram to client listeners on localhost and subnet.
        """
        payload = {
            "type": alert_type.upper(),
            "message": message,
            "timestamp": time.strftime("%H:%M:%S"),
            **(extra_data or {})
        }
        raw_bytes = json.dumps(payload).encode("utf-8")

        # Create temporary socket if main socket not bound
        sock = self._sock
        created_temp = False
        if not sock:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                created_temp = True
            except Exception as e:
                logger.error("Cannot create UDP socket for broadcast: %s", str(e))
                return False

        try:
            # Send to localhost loopback
            sock.sendto(raw_bytes, ("127.0.0.1", self.broadcast_port))
            # Send to broadcast address
            try:
                sock.sendto(raw_bytes, ("<broadcast>", self.broadcast_port))
            except Exception:
                pass
            logger.info("Dispatched UDP announcement [%s]: %s", alert_type, message)
            return True
        except Exception as e:
            logger.error("Failed to transmit UDP announcement: %s", str(e))
            return False
        finally:
            if created_temp and sock:
                try:
                    sock.close()
                except Exception:
                    pass


# Singleton instance
udp_server = UDPServer()
