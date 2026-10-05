"""
HTTP Client for IRCTC-Style Train Reservation Simulator
Manages REST requests for train running status, station schedules, and server health checks.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional
from PySide6.QtCore import QObject, QThread, Signal


class HTTPClient(QObject):
    """
    Client for interacting with RESTful endpoints of the IRCTC Simulator backend.
    """

    # Signals for asynchronous usage in UI
    health_checked = Signal(dict)
    train_status_received = Signal(dict)
    request_failed = Signal(str, str)  # (endpoint, error_message)

    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: float = 5.0, parent=None):
        super().__init__(parent)
        self.base_url: str = base_url.rstrip("/")
        self.timeout: float = timeout

    def set_base_url(self, base_url: str) -> None:
        """Update base HTTP server URL."""
        self.base_url = base_url.rstrip("/")

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Internal GET request handler using standard library urllib.
        Returns parsed JSON dict or error structure.
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            url = f"{url}?{query}"

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "IRCTC-Desktop-Client/1.0",
                "Accept": "application/json"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                status_code = response.getcode()
                raw_bytes = response.read()
                data = json.loads(raw_bytes.decode("utf-8"))
                if isinstance(data, dict):
                    if "status_code" not in data:
                        data["status_code"] = status_code
                    if "success" not in data:
                        data["success"] = (200 <= status_code < 300)
                    return data
                return {"success": True, "status_code": status_code, "data": data}

        except urllib.error.HTTPError as he:
            try:
                error_body = json.loads(he.read().decode("utf-8"))
                return {
                    "success": False,
                    "status_code": he.code,
                    "message": error_body.get("message", f"HTTP Error {he.code}: {he.reason}"),
                    "details": error_body
                }
            except Exception:
                return {
                    "success": False,
                    "status_code": he.code,
                    "message": f"HTTP {he.code}: {he.reason}"
                }

        except (TimeoutError, urllib.error.URLError) as ue:
            return {
                "success": False,
                "status_code": 0,
                "message": f"Server unreachable or timed out at {self.base_url}: {str(ue)}"
            }
        except Exception as e:
            return {
                "success": False,
                "status_code": 0,
                "message": f"HTTP Request failed: {str(e)}"
            }

    # =========================================================================
    # REST Endpoints
    # =========================================================================

    def check_health(self) -> Dict[str, Any]:
        """
        Checks server health and connectivity status.
        Queries /health or /api/health endpoint.
        """
        result = self._get("/health")
        if not result.get("success"):
            # Fallback to alternate route /api/health
            alt = self._get("/api/health")
            if alt.get("success"):
                result = alt
        return result

    def get_train_live_status(self, train_number: str, date: Optional[str] = None) -> Dict[str, Any]:
        """
        Queries live running status for a train on a given date.
        """
        params = {"date": date} if date else None
        result = self._get(f"/api/trains/{train_number.strip()}/status", params)
        if not result.get("success"):
            # Fallback query parameter route /api/status?train=
            alt = self._get("/api/status", {"train": train_number.strip(), "date": date})
            if alt.get("success"):
                result = alt
        return result

    def get_station_schedule(self, station_code: str) -> Dict[str, Any]:
        """
        Fetches scheduled departures and arrivals for a station code.
        """
        return self._get(f"/api/stations/{station_code.strip().upper()}/schedule")

    def get_system_metrics(self) -> Dict[str, Any]:
        """
        Fetches server telemetry, active socket connections, and database status.
        """
        result = self._get("/api/metrics")
        if not result.get("success"):
            alt = self._get("/metrics")
            if alt.get("success"):
                result = alt
        return result


class AsyncHttpWorker(QThread):
    """
    Convenience QThread worker to execute HTTP requests asynchronously
    without blocking the PySide6 UI thread.
    """
    result_ready = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            res = self.func(*self.args, **self.kwargs)
            self.result_ready.emit(res)
        except Exception as e:
            self.error_occurred.emit(str(e))
