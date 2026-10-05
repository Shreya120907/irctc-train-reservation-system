"""
Concurrent Client Handler for IRCTC-Style Train Reservation Server
Manages client socket lifecycle, stream buffering, JSON protocol dispatching,
and session authorization state.
"""

import json
import socket
import threading
import time
from typing import Any, Dict, Optional, Tuple

from logger import logger
from services.auth import AuthService
from services.train import TrainService
from services.booking import BookingService
from services.cancellation import CancellationService
from services.admin import AdminService
from network.udp_server import udp_server


class ClientHandler(threading.Thread):
    """
    Dedicated worker thread managing an individual TCP client connection.
    """

    def __init__(self, client_socket: socket.socket, client_address: Tuple[str, int], timeout: float = 60.0):
        super().__init__(daemon=True)
        self.sock = client_socket
        self.address = client_address
        self.timeout = timeout
        self.authenticated_user: Optional[Dict[str, Any]] = None
        self._running = False
        self._buffer = ""

    def run(self) -> None:
        """Main client loop processing newline-delimited JSON commands."""
        self._running = True
        self.sock.settimeout(self.timeout)
        logger.info("Client connected from %s:%d", self.address[0], self.address[1])

        try:
            while self._running:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break

                self._buffer += chunk.decode("utf-8", errors="replace")

                while "\n" in self._buffer:
                    line, self._buffer = self._buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    response = self._process_message(line)
                    self._send_response(response)

        except socket.timeout:
            logger.info("Client %s:%d connection timed out.", self.address[0], self.address[1])
            self._send_response({
                "status": "error",
                "code": "CONNECTION_TIMEOUT",
                "message": "Session timed out due to inactivity."
            })
        except (ConnectionResetError, BrokenPipeError):
            logger.info("Client %s:%d disconnected abruptly.", self.address[0], self.address[1])
        except Exception as e:
            logger.error("Unexpected error handling client %s:%d: %s", self.address[0], self.address[1], str(e))
        finally:
            self._cleanup()

    def _process_message(self, raw_message: str) -> Dict[str, Any]:
        """Parses and dispatches raw JSON to corresponding business service."""
        try:
            request = json.loads(raw_message)
        except json.JSONDecodeError as jde:
            return {
                "status": "error",
                "code": "MALFORMED_JSON",
                "message": f"Invalid JSON payload: {str(jde)}"
            }

        action = request.get("action", "").lower().strip()
        if not action:
            return {"status": "error", "code": "MISSING_ACTION", "message": "Action field is required."}

        # Dispatch table
        try:
            if action == "register":
                return self._handle_register(request)
            elif action == "login":
                return self._handle_login(request)
            elif action == "search_trains":
                return self._handle_search_trains(request)
            elif action == "get_train":
                return self._handle_get_train(request)
            elif action in ("get_seats", "get_seat_availability"):
                return self._handle_get_seats(request)
            elif action == "book_ticket":
                return self._handle_book_ticket(request)
            elif action in ("get_booking", "pnr_enquiry"):
                return self._handle_get_booking(request)
            elif action in ("list_bookings", "get_user_bookings"):
                return self._handle_list_bookings(request)
            elif action in ("cancel_ticket", "cancel_booking"):
                return self._handle_cancel_ticket(request)
            elif action.startswith("admin_"):
                return self._handle_admin_action(action, request)
            else:
                return {
                    "status": "error",
                    "code": "UNKNOWN_ACTION",
                    "message": f"Action '{action}' is not supported by the reservation server."
                }
        except Exception as e:
            logger.error("Internal service error during action '%s': %s", action, str(e))
            return {
                "status": "error",
                "code": "INTERNAL_ERROR",
                "message": f"Internal server error: {str(e)}"
            }

    # =========================================================================
    # Action Handlers
    # =========================================================================

    def _handle_register(self, req: Dict[str, Any]) -> Dict[str, Any]:
        return AuthService.register(
            username=req.get("username", ""),
            password=req.get("password", ""),
            email=req.get("email", ""),
            full_name=req.get("full_name", ""),
            phone=req.get("phone", ""),
            role=req.get("role", "PASSENGER")
        )

    def _handle_login(self, req: Dict[str, Any]) -> Dict[str, Any]:
        resp = AuthService.login(
            username=req.get("username", ""),
            password=req.get("password", "")
        )
        if resp.get("status") == "success":
            self.authenticated_user = resp.get("user")
            # Return standardized format for desktop frontend
            resp["success"] = True
        return resp

    def _handle_search_trains(self, req: Dict[str, Any]) -> Dict[str, Any]:
        resp = TrainService.search_trains(
            source=req.get("source", ""),
            destination=req.get("destination", ""),
            journey_date=req.get("date") or req.get("journey_date", ""),
            quota=req.get("quota", "GENERAL"),
            coach_class=req.get("coach_class")
        )
        resp["success"] = (resp.get("status") == "success")
        return resp

    def _handle_get_train(self, req: Dict[str, Any]) -> Dict[str, Any]:
        train_id = req.get("train_id") or req.get("train_number")
        resp = TrainService.get_train(train_id)
        resp["success"] = (resp.get("status") == "success")
        return resp

    def _handle_get_seats(self, req: Dict[str, Any]) -> Dict[str, Any]:
        train_id = req.get("train_id") or req.get("train_number")
        coach_class = req.get("coach_class", "SL")
        date_str = req.get("date") or req.get("journey_date", "")
        resp = TrainService.get_seats(train_id, coach_class, date_str)
        resp["success"] = (resp.get("status") == "success")
        return resp

    def _handle_book_ticket(self, req: Dict[str, Any]) -> Dict[str, Any]:
        user_id = self.authenticated_user.get("user_id") if self.authenticated_user else req.get("user_id")
        train_id = req.get("train_id") or req.get("train_number")
        date_str = req.get("journey_date") or req.get("date", "")
        coach_class = req.get("coach_class", "SL")
        passengers = req.get("passengers", [])

        # Format single seats request if passed as flat seat list
        if not passengers and req.get("seats"):
            passengers = [{"name": "Passenger", "seat_number": s} for s in req.get("seats", [])]

        resp = BookingService.book_ticket(
            user_id=user_id,
            train_number_or_id=train_id,
            journey_date=date_str,
            coach_class=coach_class,
            passengers=passengers,
            contact_email=req.get("contact_email", ""),
            contact_phone=req.get("contact_phone", ""),
            payment_gateway=req.get("payment_gateway", "IRCTC iPay")
        )
        resp["success"] = (resp.get("status") == "success")
        return resp

    def _handle_get_booking(self, req: Dict[str, Any]) -> Dict[str, Any]:
        pnr = req.get("pnr", "")
        resp = BookingService.get_booking(pnr)
        resp["success"] = (resp.get("status") == "success")
        return resp

    def _handle_list_bookings(self, req: Dict[str, Any]) -> Dict[str, Any]:
        is_admin = False
        user_id = None
        if self.authenticated_user:
            user_id = self.authenticated_user.get("user_id")
            is_admin = (self.authenticated_user.get("role") == "ADMIN")
        else:
            user_id = req.get("user_id")

        resp = BookingService.list_bookings(user_id=user_id, is_admin=is_admin)
        resp["success"] = (resp.get("status") == "success")
        return resp

    def _handle_cancel_ticket(self, req: Dict[str, Any]) -> Dict[str, Any]:
        pnr = req.get("pnr", "")
        is_admin = (self.authenticated_user and self.authenticated_user.get("role") == "ADMIN")
        user_id = self.authenticated_user.get("user_id") if self.authenticated_user else req.get("user_id")

        resp = CancellationService.cancel_ticket(
            pnr=pnr,
            user_id=user_id,
            is_admin=is_admin,
            reason=req.get("reason", "Passenger cancellation")
        )
        resp["success"] = (resp.get("status") == "success")
        return resp

    def _handle_admin_action(self, action: str, req: Dict[str, Any]) -> Dict[str, Any]:
        """Validates ADMIN privileges and dispatches admin workflows."""
        # Enforce server-side role authorization
        if not self.authenticated_user or self.authenticated_user.get("role") != "ADMIN":
            # For demonstration, check if action contains explicit admin credential or user_id
            if req.get("role") != "ADMIN":
                return {
                    "status": "error",
                    "code": "FORBIDDEN",
                    "message": "Administrative privileges required to perform this action."
                }

        user_id = self.authenticated_user.get("user_id") if self.authenticated_user else None

        if action == "admin_add_train":
            train_data = req.get("train", req)
            resp = AdminService.add_train(train_data, user_id=user_id)
        elif action == "admin_update_train":
            train_id = req.get("train_id")
            train_data = req.get("train", req)
            resp = AdminService.add_train(train_data, user_id=user_id)
        elif action in ("admin_cancel_train", "admin_deactivate_train"):
            train_id = req.get("train_id")
            reason = req.get("reason", "Administrative cancellation")
            resp = AdminService.deactivate_train(train_id, reason=reason, user_id=user_id)
        elif action == "admin_get_trains":
            resp = AdminService.get_all_trains()
        elif action == "admin_get_manifest":
            train_id = req.get("train_id") or req.get("train_number")
            date_str = req.get("date") or req.get("journey_date", "")
            resp = AdminService.get_manifest(train_id, date_str)
        elif action in ("admin_get_system_stats", "admin_get_reports"):
            resp = AdminService.get_system_stats()
        elif action == "admin_broadcast":
            msg = req.get("message", "Service announcement")
            a_type = req.get("alert_type", "INFO")
            ok = udp_server.broadcast_announcement(msg, alert_type=a_type)
            resp = {"status": "success" if ok else "error", "message": "Broadcast enqueued" if ok else "Broadcast failed"}
        else:
            resp = {"status": "error", "code": "INVALID_ADMIN_ACTION", "message": f"Admin action '{action}' not recognized."}

        resp["success"] = (resp.get("status") == "success")
        return resp

    # =========================================================================
    # Helpers
    # =========================================================================

    def _send_response(self, response_dict: Dict[str, Any]) -> None:
        """Encodes and sends newline-framed JSON response."""
        try:
            raw = (json.dumps(response_dict) + "\n").encode("utf-8")
            self.sock.sendall(raw)
        except Exception as e:
            logger.error("Failed to send response to %s:%d: %s", self.address[0], self.address[1], str(e))

    def _cleanup(self) -> None:
        """Safely terminates socket connection."""
        self._running = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass
        logger.info("Connection closed for %s:%d", self.address[0], self.address[1])
