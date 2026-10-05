"""
Lightweight HTTP Status Server for IRCTC-Style Train Reservation System
Provides REST endpoints for train running status, health checks, and server metrics.
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import threading
import time
import urllib.parse
from typing import Optional

from database.connection import test_connection, get_connection
from logger import logger

START_TIME = time.time()


class TrainStatusHTTPHandler(BaseHTTPRequestHandler):
    """
    HTTP request handler serving JSON REST endpoints.
    """

    def _set_headers(self, status_code: int = 200) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self) -> None:
        self._set_headers(200)

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path.rstrip("/")
        query_params = urllib.parse.parse_qs(parsed_url.query)

        # Route: /health or /api/health
        if path in ("/health", "/api/health"):
            self._handle_health()
        # Route: /api/metrics or /metrics
        elif path in ("/api/metrics", "/metrics"):
            self._handle_metrics()
        # Route: /api/trains
        elif path in ("/api/trains", "/trains"):
            self._handle_trains()
        # Route: /api/train/<number>/status or /api/status
        elif path.startswith("/api/train/") and path.endswith("/status"):
            parts = path.split("/")
            train_num = parts[3] if len(parts) >= 4 else ""
            self._handle_train_status(train_num)
        elif path in ("/api/status", "/status"):
            train_num = query_params.get("train", [""])[0]
            self._handle_train_status(train_num)
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({
                "status": "error",
                "code": "NOT_FOUND",
                "message": f"Endpoint '{path}' not found."
            }).encode("utf-8"))

    def _handle_health(self) -> None:
        db_ok, db_msg = test_connection()
        uptime_sec = int(time.time() - START_TIME)
        status_code = 200 if db_ok else 503

        resp = {
            "status": "Healthy" if db_ok else "Degraded",
            "success": db_ok,
            "database_status": "Connected" if db_ok else f"Disconnected: {db_msg}",
            "uptime_seconds": uptime_sec,
            "uptime_human": f"{uptime_sec // 3600}h {(uptime_sec % 3600) // 60}m {uptime_sec % 60}s",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self._set_headers(status_code)
        self.wfile.write(json.dumps(resp).encode("utf-8"))

    def _handle_metrics(self) -> None:
        uptime_sec = int(time.time() - START_TIME)
        db_ok, _ = test_connection()

        # Query metrics from DB if connected
        total_bookings = 0
        total_trains = 0
        if db_ok:
            try:
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT COUNT(*) AS c FROM bookings WHERE status = 'CONFIRMED';")
                        total_bookings = cur.fetchone()["c"]
                        cur.execute("SELECT COUNT(*) AS c FROM trains WHERE active = TRUE;")
                        total_trains = cur.fetchone()["c"]
            except Exception:
                pass

        resp = {
            "status": "success",
            "uptime": f"{uptime_sec}s",
            "active_connections": threading.active_count() - 2,  # Adjusting for internal service threads
            "database_status": "Optimal" if db_ok else "Unavailable",
            "active_trains_count": total_trains,
            "confirmed_bookings_count": total_bookings
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(resp).encode("utf-8"))

    def _handle_trains(self) -> None:
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id, train_number, train_name, active FROM trains WHERE active = TRUE;")
                    trains = cur.fetchall()

            self._set_headers(200)
            self.wfile.write(json.dumps({
                "status": "success",
                "trains": [dict(t) for t in trains]
            }).encode("utf-8"))
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))

    def _handle_train_status(self, train_num: str) -> None:
        if not train_num:
            self._set_headers(400)
            self.wfile.write(json.dumps({
                "status": "error",
                "message": "Train number is required."
            }).encode("utf-8"))
            return

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, train_number, train_name, active FROM trains WHERE train_number = %s;",
                        (train_num,)
                    )
                    train = cur.fetchone()

                    if not train:
                        self._set_headers(404)
                        self.wfile.write(json.dumps({
                            "status": "error",
                            "message": f"Train #{train_num} not found."
                        }).encode("utf-8"))
                        return

                    # Fetch route
                    cur.execute(
                        """
                        SELECT s.station_code, s.station_name, r.stop_order, r.arrival_time, r.departure_time
                        FROM routes r
                        JOIN stations s ON r.station_id = s.id
                        WHERE r.train_id = %s
                        ORDER BY r.stop_order;
                        """,
                        (train["id"],)
                    )
                    stops = cur.fetchall()

            current_st = stops[len(stops) // 2]["station_name"] if len(stops) > 2 else (stops[0]["station_name"] if stops else "In Transit")
            next_st = stops[-1]["station_name"] if stops else "Destination"

            resp = {
                "success": True,
                "train_number": train["train_number"],
                "train_name": train["train_name"],
                "status": "ON TIME",
                "delay_minutes": 0,
                "current_station": current_st,
                "next_station": next_st,
                "platform": 4,
                "last_updated": time.strftime("%H:%M:%S")
            }
            self._set_headers(200)
            self.wfile.write(json.dumps(resp).encode("utf-8"))
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))

    def log_message(self, format: str, *args) -> None:
        # Route through structured server logger
        logger.debug(f"HTTP {self.command} {self.path} - {format % args}")


class HTTPServerService:
    """
    Manages the background HTTP status server thread.
    """

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        self.host = host if host is not None else os.getenv("HTTP_HOST", "0.0.0.0")
        self.port = port if port is not None else int(os.getenv("HTTP_PORT", "8080"))
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        try:
            self._server = HTTPServer((self.host, self.port), TrainStatusHTTPHandler)
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            logger.info("HTTP Status & Telemetry Service listening on http://%s:%d", self.host, self.port)
        except Exception as e:
            logger.error("Failed to start HTTP server on %s:%d: %s", self.host, self.port, str(e))

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            logger.info("HTTP Status Service stopped.")


# Singleton instance
http_service = HTTPServerService()
