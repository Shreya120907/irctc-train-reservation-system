"""
TCP Client for IRCTC-Style Train Reservation Simulator
Handles core transactional workflows via JSON messaging over a TCP socket.
Zero direct database access - all operations route through this network interface.
"""

import json
import socket
import threading
from typing import Any, Dict, List, Optional, Tuple


class NetworkError(Exception):
    """Custom exception raised when network operations fail."""
    pass


class TCPClient:
    """
    Thread-safe TCP client for bidirectional JSON messaging with the IRCTC backend server.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 9000, timeout: float = 8.0):
        self.host: str = host
        self.port: int = port
        self.timeout: float = timeout
        self._socket: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._buffer: str = ""
        self.current_user: Optional[Dict[str, Any]] = None

    def connect(self, host: Optional[str] = None, port: Optional[int] = None) -> Tuple[bool, str]:
        """
        Establishes a TCP connection to the server.
        Returns a tuple of (success_bool, message_str).
        """
        with self._lock:
            if host:
                self.host = host
            if port:
                self.port = port

            # Disconnect existing connection if any
            self._close_socket()

            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                sock.connect((self.host, self.port))
                self._socket = sock
                self._buffer = ""
                return True, f"Connected to server at {self.host}:{self.port}"
            except socket.timeout:
                self._close_socket()
                return False, f"Connection timed out connecting to {self.host}:{self.port}"
            except ConnectionRefusedError:
                self._close_socket()
                return False, f"Connection refused by server at {self.host}:{self.port}"
            except Exception as e:
                self._close_socket()
                return False, f"Unable to connect to server: {str(e)}"

    def disconnect(self) -> None:
        """Gracefully closes the connection."""
        with self._lock:
            self._close_socket()

    def _close_socket(self) -> None:
        """Internal helper to close socket without locking (must be called with lock held)."""
        if self._socket:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        self._buffer = ""

    def is_connected(self) -> bool:
        """Checks if the client is currently connected."""
        with self._lock:
            return self._socket is not None

    def send_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sends a JSON payload over TCP terminated with a newline and awaits the JSON response.
        Thread-safe, handles reconnections, buffering, and timeouts.
        Returns the parsed response dictionary or an error dictionary.
        """
        with self._lock:
            if not self._socket:
                # Attempt automatic reconnect
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(self.timeout)
                    sock.connect((self.host, self.port))
                    self._socket = sock
                    self._buffer = ""
                except Exception as e:
                    return {
                        "status": "error",
                        "success": False,
                        "message": f"Server connection unavailable ({self.host}:{self.port}): {str(e)}"
                    }

            try:
                # Attach authentication token if logged in
                if self.current_user and "token" in self.current_user and "token" not in payload:
                    payload["token"] = self.current_user["token"]

                # Serialize and send message with newline framing
                raw_data = (json.dumps(payload) + "\n").encode("utf-8")
                self._socket.sendall(raw_data)

                # Receive response until newline is reached
                while "\n" not in self._buffer:
                    chunk = self._socket.recv(4096)
                    if not chunk:
                        self._close_socket()
                        return {
                            "status": "error",
                            "success": False,
                            "message": "Server closed the connection unexpectedly."
                        }
                    self._buffer += chunk.decode("utf-8", errors="replace")

                # Extract first complete message
                line, self._buffer = self._buffer.split("\n", 1)
                response = json.loads(line.strip())

                # Standardize success flag if not explicitly present
                if "success" not in response:
                    response["success"] = (response.get("status") in ("success", "ok"))

                return response

            except socket.timeout:
                self._close_socket()
                return {
                    "status": "error",
                    "success": False,
                    "message": "Request timed out waiting for server response."
                }
            except json.JSONDecodeError as jde:
                return {
                    "status": "error",
                    "success": False,
                    "message": f"Malformed response from server: {str(jde)}"
                }
            except Exception as e:
                self._close_socket()
                return {
                    "status": "error",
                    "success": False,
                    "message": f"Communication failure: {str(e)}"
                }

    # =========================================================================
    # Core Transactional Workflows
    # =========================================================================

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """Authenticates user credentials."""
        request = {
            "action": "login",
            "username": username.strip(),
            "password": password
        }
        response = self.send_request(request)
        if response.get("success"):
            self.current_user = response.get("user", {})
            # Ensure minimal keys exist
            if "username" not in self.current_user:
                self.current_user["username"] = username.strip()
            if "role" not in self.current_user:
                self.current_user["role"] = response.get("role", "passenger")
        return response

    def logout(self) -> None:
        """Clears local user session state."""
        self.current_user = None

    def register(
        self,
        username: str,
        password: str,
        email: str,
        full_name: str,
        phone: str = "",
        role: str = "passenger"
    ) -> Dict[str, Any]:
        """Registers a new user account."""
        request = {
            "action": "register",
            "username": username.strip(),
            "password": password,
            "email": email.strip().lower(),
            "full_name": full_name.strip(),
            "phone": phone.strip(),
            "role": role
        }
        return self.send_request(request)

    def search_trains(
        self,
        source: str,
        destination: str,
        date: str,
        quota: str = "GENERAL",
        coach_class: Optional[str] = None
    ) -> Dict[str, Any]:
        """Searches trains matching the route and date filters."""
        request = {
            "action": "search_trains",
            "source": source.strip().upper(),
            "destination": destination.strip().upper(),
            "date": date,
            "quota": quota.upper(),
            "coach_class": coach_class
        }
        return self.send_request(request)

    def get_seat_availability(
        self,
        train_id: Any,
        coach_class: str,
        date: str
    ) -> Dict[str, Any]:
        """Fetches dynamic seat availability and layout matrix for a train/coach."""
        request = {
            "action": "get_seats",
            "train_id": train_id,
            "coach_class": coach_class.upper(),
            "date": date
        }
        return self.send_request(request)

    def book_ticket(self, booking_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes an atomic booking transaction.
        Payload should include train_id, source, destination, date, coach_class,
        quota, passengers list, and optional seat preferences.
        """
        request = {
            "action": "book_ticket",
            **booking_payload
        }
        if self.current_user:
            request["user_id"] = self.current_user.get("user_id")
            request["booked_by"] = self.current_user.get("username")
        return self.send_request(request)

    def cancel_booking(
        self,
        pnr: str,
        seat_numbers: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Cancels a booking or specific seats by PNR."""
        request = {
            "action": "cancel_booking",
            "pnr": pnr.strip(),
            "seat_numbers": seat_numbers or []
        }
        if self.current_user:
            request["user_id"] = self.current_user.get("user_id")
        return self.send_request(request)

    def pnr_enquiry(self, pnr: str) -> Dict[str, Any]:
        """Queries the current status, chart preparation, and passengers for a PNR."""
        request = {
            "action": "pnr_enquiry",
            "pnr": pnr.strip()
        }
        return self.send_request(request)

    def get_user_bookings(self, user_id: Optional[Any] = None) -> Dict[str, Any]:
        """Retrieves booking history for the current or specified user."""
        target_uid = user_id or (self.current_user.get("user_id") if self.current_user else None)
        request = {
            "action": "get_user_bookings",
            "user_id": target_uid,
            "username": self.current_user.get("username") if self.current_user else None
        }
        return self.send_request(request)

    # =========================================================================
    # Admin Operations
    # =========================================================================

    def admin_get_trains(self) -> Dict[str, Any]:
        """Retrieves catalog of all registered trains for administration."""
        request = {"action": "admin_get_trains"}
        return self.send_request(request)

    def admin_add_train(self, train_data: Dict[str, Any]) -> Dict[str, Any]:
        """Adds a new train schedule and coach layout."""
        request = {
            "action": "admin_add_train",
            "train": train_data
        }
        return self.send_request(request)

    def admin_update_train(self, train_id: Any, train_data: Dict[str, Any]) -> Dict[str, Any]:
        """Updates train configuration, timings, or active status."""
        request = {
            "action": "admin_update_train",
            "train_id": train_id,
            "train": train_data
        }
        return self.send_request(request)

    def admin_cancel_train(self, train_id: Any, reason: str = "") -> Dict[str, Any]:
        """Cancels a train run and triggers automated refund status."""
        request = {
            "action": "admin_cancel_train",
            "train_id": train_id,
            "reason": reason
        }
        return self.send_request(request)

    def admin_get_manifest(self, train_id: Any, date: str) -> Dict[str, Any]:
        """Retrieves the official passenger manifest for a train on a given date."""
        request = {
            "action": "admin_get_manifest",
            "train_id": train_id,
            "date": date
        }
        return self.send_request(request)

    def admin_broadcast_alert(self, message: str, alert_type: str = "INFO") -> Dict[str, Any]:
        """Instructs the server to broadcast an alert to clients."""
        request = {
            "action": "admin_broadcast",
            "message": message,
            "alert_type": alert_type
        }
        return self.send_request(request)

    def admin_get_system_stats(self) -> Dict[str, Any]:
        """Fetches administrative telemetry, ticket revenue, and load statistics."""
        request = {"action": "admin_get_system_stats"}
        return self.send_request(request)
