"""
FTP Service for IRCTC Train Reservation System
Provides automated generation and transfer of electronic reservation slips (ERS),
cancellation reports, and administrative audit manifests.
Includes an embedded local RFC-959 compliant FTP server for academic demonstration.
"""

from datetime import datetime
import ftplib
import os
import socket
import threading
from typing import Any, Dict, Optional

from logger import logger


class EmbeddedFTPServer:
    """
    Lightweight RFC-959 compliant FTP server daemon for ticket and report transfer.
    Runs locally on configurable port (default 2121).
    """

    def __init__(self, root_dir: str = "files", host: str = "127.0.0.1", port: int = 2121, user: str = "irctc_ftp", password: str = "ftp_secret_pass"):
        self.root_dir = os.path.abspath(root_dir)
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self._server_sock: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        os.makedirs(os.path.join(self.root_dir, "tickets"), exist_ok=True)
        os.makedirs(os.path.join(self.root_dir, "reports"), exist_ok=True)

        try:
            self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.bind((self.host, self.port))
            self._server_sock.listen(5)
            self._running = True

            self._thread = threading.Thread(target=self._accept_loop, daemon=True)
            self._thread.start()
            logger.info("Embedded FTP Service listening on ftp://%s:%d (User: %s)", self.host, self.port, self.user)
        except Exception as e:
            logger.error("Failed to start Embedded FTP server: %s", str(e))

    def _accept_loop(self) -> None:
        while self._running:
            try:
                client_sock, addr = self._server_sock.accept()
                threading.Thread(target=self._handle_ftp_client, args=(client_sock,), daemon=True).start()
            except Exception:
                break

    def _handle_ftp_client(self, sock: socket.socket) -> None:
        """Handles an individual FTP control connection."""
        pasv_sock: Optional[socket.socket] = None
        cwd = self.root_dir
        authenticated = False

        try:
            sock.sendall(b"220 IRCTC Electronic Ticket Repository FTP Ready\r\n")

            while True:
                line = sock.recv(1024)
                if not line:
                    break

                cmd_parts = line.decode("utf-8", errors="replace").strip().split(" ", 1)
                cmd = cmd_parts[0].upper()
                arg = cmd_parts[1] if len(cmd_parts) > 1 else ""

                if cmd == "USER":
                    if arg == self.user:
                        sock.sendall(b"331 User name okay, need password.\r\n")
                    else:
                        sock.sendall(b"331 User name okay, need password.\r\n")
                elif cmd == "PASS":
                    authenticated = True
                    sock.sendall(b"230 User logged in, proceed.\r\n")
                elif cmd == "SYST":
                    sock.sendall(b"215 UNIX Type: L8\r\n")
                elif cmd == "PWD":
                    rel = os.path.relpath(cwd, self.root_dir)
                    sock.sendall(f'257 "/{rel}" is current directory.\r\n'.encode("utf-8"))
                elif cmd == "TYPE":
                    sock.sendall(b"200 Command okay.\r\n")
                elif cmd in ("PASV", "EPSV"):
                    if pasv_sock:
                        try:
                            pasv_sock.close()
                        except Exception:
                            pass
                    pasv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    pasv_sock.bind((self.host, 0))
                    pasv_sock.listen(1)
                    p_port = pasv_sock.getsockname()[1]
                    p1, p2 = p_port // 256, p_port % 256
                    h_parts = self.host.replace(".", ",")
                    sock.sendall(f"227 Entering Passive Mode ({h_parts},{p1},{p2}).\r\n".encode("utf-8"))
                elif cmd == "LIST":
                    sock.sendall(b"150 File status okay; about to open data connection.\r\n")
                    if pasv_sock:
                        try:
                            data_conn, _ = pasv_sock.accept()
                            listing = ""
                            for item in os.listdir(cwd):
                                full = os.path.join(cwd, item)
                                is_dir = "d" if os.path.isdir(full) else "-"
                                size = os.path.getsize(full) if not os.path.isdir(full) else 4096
                                listing += f"{is_dir}rwxr-xr-x 1 owner group {size} Oct 01 12:00 {item}\r\n"
                            data_conn.sendall(listing.encode("utf-8"))
                            data_conn.close()
                            sock.sendall(b"226 Closing data connection.\r\n")
                        except Exception as e:
                            sock.sendall(f"425 Cannot open data connection: {str(e)}\r\n".encode("utf-8"))
                        finally:
                            pasv_sock.close()
                            pasv_sock = None
                elif cmd == "RETR":
                    target_file = os.path.join(cwd, os.path.basename(arg))
                    if os.path.exists(target_file) and os.path.isfile(target_file):
                        sock.sendall(b"150 Opening binary mode data connection.\r\n")
                        if pasv_sock:
                            try:
                                data_conn, _ = pasv_sock.accept()
                                with open(target_file, "rb") as f:
                                    data_conn.sendall(f.read())
                                data_conn.close()
                                sock.sendall(b"226 Transfer complete.\r\n")
                            except Exception as e:
                                sock.sendall(f"426 Connection closed; transfer aborted: {str(e)}\r\n".encode("utf-8"))
                            finally:
                                pasv_sock.close()
                                pasv_sock = None
                    else:
                        sock.sendall(b"550 File not found.\r\n")
                elif cmd == "QUIT":
                    sock.sendall(b"221 Service closing control connection.\r\n")
                    break
                else:
                    sock.sendall(b"502 Command not implemented.\r\n")
        except Exception:
            pass
        finally:
            if pasv_sock:
                try:
                    pasv_sock.close()
                except Exception:
                    pass
            sock.close()

    def stop(self) -> None:
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None


class FTPService:
    """
    Client and generator interface for ticketing and reporting file artifacts.
    """

    def __init__(self):
        self.files_dir = os.path.abspath(os.getenv("FTP_DIR", "files"))
        self.tickets_dir = os.path.join(self.files_dir, "tickets")
        self.reports_dir = os.path.join(self.files_dir, "reports")
        self.server: Optional[EmbeddedFTPServer] = None

    def start_embedded_server(self) -> None:
        host = os.getenv("FTP_HOST", "127.0.0.1")
        port = int(os.getenv("FTP_PORT", "2121"))
        user = os.getenv("FTP_USER", "irctc_ftp")
        password = os.getenv("FTP_PASSWORD", "ftp_secret_pass")

        self.server = EmbeddedFTPServer(self.files_dir, host=host, port=port, user=user, password=password)
        self.server.start()

    def stop(self) -> None:
        if self.server:
            self.server.stop()
            self.server = None

    def generate_ticket_file(self, booking_data: Dict[str, Any]) -> str:
        """
        Creates an official formatted text ticket (ERS) stored in files/tickets/.
        """
        os.makedirs(self.tickets_dir, exist_ok=True)
        pnr = booking_data.get("pnr", "UNKNOWN")
        file_path = os.path.join(self.tickets_dir, f"ticket_{pnr}.txt")

        passengers_txt = ""
        for p in booking_data.get("passengers", []):
            passengers_txt += (
                f"  - {p.get('name', 'Passenger')} | Age: {p.get('age', '--')} | "
                f"Gender: {p.get('gender', '--')} | Coach: {p.get('coach', 'S1')} | "
                f"Seat: {p.get('seat_number', '--')} ({p.get('berth', 'B')})\n"
            )

        content = f"""================================================================================
                    INDIAN RAILWAYS PASSENGER RESERVATION SYSTEM
                         ELECTRONIC RESERVATION SLIP (ERS)
================================================================================
PNR Number       : {pnr}
Booking Status   : {booking_data.get('status', 'CONFIRMED')}
Train Number/Name: {booking_data.get('train_number')} - {booking_data.get('train_name')}
Date of Journey  : {booking_data.get('journey_date')}
Coach & Class    : {booking_data.get('coach_class')} ({booking_data.get('coach_number', 'C1')})
Total Fare Paid  : Rs. {float(booking_data.get('total_fare', 0.0)):.2f}
Payment Gateway  : {booking_data.get('payment_gateway', 'IRCTC iPay')}
Timestamp        : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
--------------------------------------------------------------------------------
PASSENGER ROSTER:
{passengers_txt}--------------------------------------------------------------------------------
RULES & ADVISORIES:
1. Valid original Photo Identity Proof required during travel.
2. Please check platform display screens for coach sequencing.
3. This e-ticket is issued electronically via IRCTC Simulator File Gateway.
================================================================================
"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info("Generated e-ticket file for PNR %s: %s", pnr, file_path)
        return file_path

    def generate_cancellation_report(self, cancel_data: Dict[str, Any]) -> str:
        """
        Creates a cancellation certificate and refund voucher in files/reports/.
        """
        os.makedirs(self.reports_dir, exist_ok=True)
        pnr = cancel_data.get("pnr", "UNKNOWN")
        file_path = os.path.join(self.reports_dir, f"cancellation_{pnr}.txt")

        content = f"""================================================================================
                   INDIAN RAILWAYS - CANCELLATION & REFUND ADVICE
================================================================================
PNR Number       : {pnr}
Cancellation Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Train Number     : {cancel_data.get('train_number')} - {cancel_data.get('train_name')}
Date of Journey  : {cancel_data.get('journey_date')}
Original Fare    : Rs. {float(cancel_data.get('total_fare', 0.0)):.2f}
Clerkage Charge  : Rs. {float(cancel_data.get('cancellation_charge', 0.0)):.2f}
Net Refund Amount: Rs. {float(cancel_data.get('refund_amount', 0.0)):.2f}
--------------------------------------------------------------------------------
Refund will be credited to original payment source within 3-5 banking days.
================================================================================
"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info("Generated cancellation report for PNR %s: %s", pnr, file_path)
        return file_path


# Singleton instance
ftp_service = FTPService()
