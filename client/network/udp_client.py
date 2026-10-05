"""
UDP Client for IRCTC-Style Train Reservation Simulator
Runs as a background QThread listening on a configurable UDP port
for lightweight asynchronous notifications and live server announcements.
"""

import json
import socket
import time
from typing import Optional
from PySide6.QtCore import QThread, Signal


class UDPClient(QThread):
    """
    Background worker thread listening on a UDP port for real-time broadcasts
    such as delay alerts, platform changes, tatkal opening alerts, and emergency advisories.
    """

    # Signals for UI integration
    announcement_received = Signal(dict)       # Structured announcement {type, title, message, timestamp}
    raw_notification_received = Signal(str)    # Fallback plain text alert
    listener_status = Signal(bool, str)        # (is_active, status_message)

    def __init__(self, port: int = 9999, bind_ip: str = "0.0.0.0", parent=None):
        super().__init__(parent)
        self.port: int = port
        self.bind_ip: str = bind_ip
        self._running: bool = False
        self._sock: Optional[socket.socket] = None

    def configure(self, port: int, bind_ip: str = "0.0.0.0") -> None:
        """Update listening port and interface (thread should be stopped before changing)."""
        self.port = port
        self.bind_ip = bind_ip

    def run(self) -> None:
        """Main listening loop executed in background QThread."""
        self._running = True

        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Allow multiple sockets to bind to the same broadcast port if supported
            try:
                self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            except Exception:
                pass
            try:
                self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            except Exception:
                pass

            self._sock.bind((self.bind_ip, self.port))
            self._sock.settimeout(1.0)  # Periodic timeout to allow clean thread shutdown
            self.listener_status.emit(True, f"Listening for live broadcasts on UDP port {self.port}")
        except Exception as e:
            self._running = False
            self.listener_status.emit(False, f"UDP Bind Error on port {self.port}: {str(e)}")
            return

        while self._running:
            try:
                data, addr = self._sock.recvfrom(65535)
                if not data:
                    continue

                raw_text = data.decode("utf-8", errors="replace").strip()
                if not raw_text:
                    continue

                # Emit raw signal
                self.raw_notification_received.emit(raw_text)

                # Attempt to parse structured JSON announcement
                try:
                    payload = json.loads(raw_text)
                    if isinstance(payload, dict):
                        # Ensure baseline fields exist
                        if "timestamp" not in payload:
                            payload["timestamp"] = time.strftime("%H:%M:%S")
                        if "type" not in payload:
                            payload["type"] = "ALERT"
                        self.announcement_received.emit(payload)
                    else:
                        self.announcement_received.emit({
                            "type": "BROADCAST",
                            "message": raw_text,
                            "timestamp": time.strftime("%H:%M:%S"),
                            "sender": f"{addr[0]}:{addr[1]}"
                        })
                except json.JSONDecodeError:
                    # Plain string broadcast
                    self.announcement_received.emit({
                        "type": "BROADCAST",
                        "message": raw_text,
                        "timestamp": time.strftime("%H:%M:%S"),
                        "sender": f"{addr[0]}:{addr[1]}"
                    })

            except socket.timeout:
                # Normal timeout; loop back to check self._running
                continue
            except Exception as e:
                if self._running:
                    # Only report errors if we haven't initiated shutdown
                    self.listener_status.emit(False, f"UDP Receive Error: {str(e)}")
                break

        # Cleanup socket on exit
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

        self.listener_status.emit(False, "UDP Broadcast listener stopped.")

    def stop(self) -> None:
        """Signals the background thread to terminate and waits for completion."""
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self.wait(2000)
