"""
Backend Integration Test Suite for IRCTC Server
Verifies multi-protocol engines (TCP, UDP, HTTP, FTP, SMTP), services, and data validation.
"""

import ftplib
import json
import os
import socket
import sys
import time
import urllib.request

sys.path.insert(0, "server")
sys.path.insert(0, ".")

from services.auth import AuthService
from services.train import TrainService
from services.booking import BookingService
from services.cancellation import CancellationService
from services.admin import AdminService

from network.udp_server import UDPServer
from network.http_server import HTTPServerService
from network.ftp_service import FTPService, EmbeddedFTPServer
from network.smtp_service import SMTPService
from tcp_server import TCPServer


def run_tests():
    print("================================================================================")
    print("        RUNNING COMPREHENSIVE BACKEND PROTOCOL & SERVICES VERIFICATION")
    print("================================================================================")

    # -------------------------------------------------------------------------
    # 1. Auth Service & Password Security Tests
    # -------------------------------------------------------------------------
    print("\n[TEST 1] Testing Password Hashing & Security...")
    plain_pw = "SuperSecure123!"
    pw_hash = AuthService.hash_password(plain_pw)
    assert pw_hash.startswith("$2b$") or pw_hash.startswith("$2a$"), "Invalid bcrypt format"
    assert AuthService.verify_password(plain_pw, pw_hash) is True, "Password verification failed"
    assert AuthService.verify_password("WrongPassword", pw_hash) is False, "Password falsely verified"
    print("PASS: Bcrypt password hashing & validation verified.")

    # -------------------------------------------------------------------------
    # 2. Input Validation Tests
    # -------------------------------------------------------------------------
    print("\n[TEST 2] Testing Pre-Flight Input Validations...")
    inv_reg = AuthService.register("ab", "123", "bademail", "")
    assert inv_reg.get("status") == "error", "Registration should reject empty full name"

    inv_email = AuthService.register("user1", "secret123", "not-an-email", "User One")
    assert inv_email.get("status") == "error" and inv_email.get("code") == "INVALID_EMAIL", "Failed email validation"

    inv_pw = AuthService.register("user1", "123", "user1@example.com", "User One")
    assert inv_pw.get("status") == "error" and inv_pw.get("code") == "WEAK_PASSWORD", "Failed password strength check"
    print("PASS: Pre-flight input constraints strictly enforced.")

    # -------------------------------------------------------------------------
    # 3. UDP Broadcast Transmission Tests
    # -------------------------------------------------------------------------
    print("\n[TEST 3] Testing UDP Broadcast Service...")
    udp = UDPServer(port=6005, target_broadcast_port=9998)
    udp.start()

    # Create listener socket on port 9998
    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv_sock.bind(("127.0.0.1", 9998))
    recv_sock.settimeout(2.0)

    # Dispatch broadcast
    test_msg = "Train 12301 arriving on Platform 4"
    udp.broadcast_announcement(test_msg, alert_type="PLATFORM")

    data, _ = recv_sock.recvfrom(4096)
    ann = json.loads(data.decode("utf-8"))
    assert ann.get("message") == test_msg, f"Unexpected message: {ann}"
    assert ann.get("type") == "PLATFORM", f"Unexpected type: {ann}"

    recv_sock.close()
    udp.stop()
    print("PASS: UDP datagram notification broadcasting verified.")

    # -------------------------------------------------------------------------
    # 4. HTTP REST API Tests
    # -------------------------------------------------------------------------
    print("\n[TEST 4] Testing HTTP Status & Telemetry REST API...")
    http = HTTPServerService(host="127.0.0.1", port=8085)
    http.start()
    time.sleep(0.5)

    # Test /health
    req = urllib.request.Request("http://127.0.0.1:8085/health")
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            code = resp.getcode()
            h_data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        code = err.code
        h_data = json.loads(err.read().decode())

    assert code in (200, 503), f"Unexpected HTTP status: {code}"
    assert "uptime_seconds" in h_data, "Uptime missing in health response"
    print(f"  - Health Endpoint: HTTP {code} - Status: {h_data.get('status')} (Uptime: {h_data.get('uptime_human')})")

    # Test /api/metrics
    req_m = urllib.request.Request("http://127.0.0.1:8085/api/metrics")
    with urllib.request.urlopen(req_m, timeout=3.0) as resp:
        assert resp.getcode() == 200
        m_data = json.loads(resp.read().decode())
        assert "active_connections" in m_data, "Metrics missing active connections"
        print(f"  - Metrics Endpoint: active_connections={m_data.get('active_connections')}")

    http.stop()
    print("PASS: HTTP REST endpoints verified.")

    # -------------------------------------------------------------------------
    # 5. FTP Service & ERS Ticket File Generation Tests
    # -------------------------------------------------------------------------
    print("\n[TEST 5] Testing FTP Service & Ticket File Generation...")
    sample_booking = {
        "pnr": "2459988776",
        "train_number": "12301",
        "train_name": "Howrah Rajdhani Express",
        "journey_date": "2026-10-15",
        "coach_class": "3A",
        "coach_number": "B1",
        "seats": ["B1-21", "B1-22"],
        "total_fare": 3100.0,
        "payment_gateway": "IRCTC iPay",
        "passengers": [
            {"name": "Ananya Sen", "age": 28, "gender": "Female", "coach": "B1", "seat_number": "21", "berth": "LB"},
            {"name": "Rohan Sen", "age": 31, "gender": "Male", "coach": "B1", "seat_number": "22", "berth": "MB"}
        ]
    }

    ftp = FTPService()
    ticket_path = ftp.generate_ticket_file(sample_booking)
    assert os.path.exists(ticket_path), "Ticket file was not generated"

    with open(ticket_path, "r", encoding="utf-8") as f:
        ticket_text = f.read()
        assert "2459988776" in ticket_text, "PNR missing in ticket file"
        assert "Ananya Sen" in ticket_text, "Passenger missing in ticket file"
    print(f"  - Generated Ticket: {ticket_path} ({os.path.getsize(ticket_path)} bytes)")

    # Test embedded FTP server
    ftp_server = EmbeddedFTPServer(root_dir="files", host="127.0.0.1", port=2125, user="irctc_ftp", password="ftp_secret_pass")
    ftp_server.start()
    time.sleep(0.5)

    client_ftp = ftplib.FTP()
    client_ftp.connect("127.0.0.1", 2125, timeout=3.0)
    client_ftp.login("irctc_ftp", "ftp_secret_pass")
    files_list = []
    client_ftp.retrlines("LIST", files_list.append)
    assert len(files_list) > 0, "FTP file listing should not be empty"
    client_ftp.quit()
    ftp_server.stop()
    print("PASS: FTP file generation and embedded RFC-959 FTP daemon verified.")

    # -------------------------------------------------------------------------
    # 6. SMTP Notification Service Tests
    # -------------------------------------------------------------------------
    print("\n[TEST 6] Testing SMTP Notification Service...")
    smtp = SMTPService()
    sample_booking["contact_email"] = "passenger@domain.com"
    email_ok = smtp.send_booking_email(sample_booking)
    assert email_ok is True, "Booking email dispatch or archive failed"
    print("PASS: SMTP email generation and archival verified.")

    # -------------------------------------------------------------------------
    # 7. Core Multithreaded TCP Server & ClientHandler Tests
    # -------------------------------------------------------------------------
    print("\n[TEST 7] Testing Multithreaded TCP Server & Protocol Dispatcher...")
    tcp_server = TCPServer(host="127.0.0.1", port=5005)
    tcp_server.start()
    time.sleep(0.5)

    # Connect TCP Client Socket
    client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_sock.connect(("127.0.0.1", 5005))

    # Send unknown action request
    req = json.dumps({"action": "unknown_action"}) + "\n"
    client_sock.sendall(req.encode("utf-8"))

    raw_resp = client_sock.recv(4096).decode("utf-8")
    resp = json.loads(raw_resp.strip())
    assert resp.get("status") == "error" and resp.get("code") == "UNKNOWN_ACTION", f"Unexpected response: {resp}"
    print("  - Handled invalid action with structured error shielding.")

    # Send search trains request
    req_search = json.dumps({
        "action": "search_trains",
        "source": "NDLS",
        "destination": "BCT",
        "date": "2026-10-15"
    }) + "\n"
    client_sock.sendall(req_search.encode("utf-8"))

    raw_resp2 = client_sock.recv(4096).decode("utf-8")
    resp2 = json.loads(raw_resp2.strip())
    assert "status" in resp2, "Status missing in search response"
    print(f"  - Processed TCP search_trains request (Status: {resp2.get('status')}).")

    client_sock.close()
    tcp_server.stop()
    print("PASS: Multithreaded TCP engine and JSON stream dispatching verified.")

    print("\n================================================================================")
    print("       ALL 7 BACKEND SUBSYSTEM VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("================================================================================")


if __name__ == "__main__":
    run_tests()
