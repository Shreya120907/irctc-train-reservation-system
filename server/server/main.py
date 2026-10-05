"""
Main Server Application Entry Point for IRCTC-Style Train Reservation System
Initializes database connections, orchestrates concurrent networking daemons
(TCP, UDP, HTTP, FTP, SMTP), and coordinates graceful system shutdown.
"""

import os
import signal
import sys
import time

# Ensure current and parent directory are accessible on sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv()

from database.connection import test_connection, init_database
from logger import logger
from tcp_server import TCPServer
from network.udp_server import udp_server
from network.http_server import http_service
from network.ftp_service import ftp_service
from network.smtp_service import smtp_service


class ServerOrchestrator:
    """
    Coordinates lifecycle of the core reservation backend and integrated networking services.
    """

    def __init__(self):
        self.tcp_server = TCPServer()
        self._running = False

    def start(self) -> None:
        logger.info("================================================================================")
        logger.info("   Starting IRCTC-Style Distributed Train Reservation Backend System")
        logger.info("================================================================================")

        # 1. Database Connection & Schema Verification
        self._setup_database()

        # 2. Launch Networking Daemons
        self._start_services()

        self._running = True
        logger.info("✓ System ready: Accepting reservations on TCP port %s", self.tcp_server.port)

        # Keep server running until signal interruption
        try:
            while self._running:
                time.sleep(1.0)
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received.")
        finally:
            self.stop()

    def _setup_database(self) -> None:
        """Verifies PostgreSQL connectivity and ensures tables are seeded."""
        db_ok, msg = test_connection()
        if db_ok:
            logger.info("✓ PostgreSQL database connection established.")
        else:
            logger.warning("PostgreSQL check note: %s", msg)
            logger.info("Attempting automatic database initialization / schema application...")
            schema_file = os.path.join(PROJECT_ROOT, "database", "schema.sql")
            seed_file = os.path.join(PROJECT_ROOT, "database", "seed.sql")
            init_ok, init_msg = init_database(schema_file, seed_file)
            if init_ok:
                logger.info("✓ %s", init_msg)
            else:
                logger.warning("Database setup notice: %s", init_msg)
                logger.warning("Please ensure PostgreSQL is running and DB_PASSWORD in .env is correct.")

    def _start_services(self) -> None:
        """Starts TCP, UDP, HTTP, FTP, and SMTP services."""
        # 1. UDP Notification Server
        try:
            udp_server.start()
            logger.info("✓ UDP Broadcast Service active on port %s", udp_server.port)
        except Exception as e:
            logger.error("UDP startup failed: %s", str(e))

        # 2. HTTP Status & Telemetry Service
        try:
            http_service.start()
            logger.info("✓ HTTP Status REST API active on port %s", http_service.port)
        except Exception as e:
            logger.error("HTTP startup failed: %s", str(e))

        # 3. FTP File Gateway
        try:
            ftp_service.start_embedded_server()
            logger.info("✓ FTP Ticketing Gateway active on port 2121")
        except Exception as e:
            logger.error("FTP startup failed: %s", str(e))

        # 4. SMTP Notification Service
        logger.info("✓ SMTP Notification Dispatcher initialized (Relay: %s:%s)", smtp_service.host, smtp_service.port)

        # 5. Core TCP Server
        try:
            self.tcp_server.start()
            logger.info("✓ TCP Core Reservation Listener active on port %s", self.tcp_server.port)
        except Exception as e:
            logger.critical("Fatal: Could not start TCP server: %s", str(e))
            sys.exit(1)

    def stop(self) -> None:
        """Gracefully halts all active services."""
        if not self._running:
            return
        self._running = False

        logger.info("Initiating graceful shutdown sequence...")
        try:
            self.tcp_server.stop()
        except Exception:
            pass

        try:
            udp_server.stop()
        except Exception:
            pass

        try:
            http_service.stop()
        except Exception:
            pass

        try:
            ftp_service.stop()
        except Exception:
            pass

        logger.info("IRCTC Train Reservation Server cleanly stopped.")


def main():
    server = ServerOrchestrator()

    # Register OS signal handlers for graceful termination
    def handle_signal(signum, frame):
        logger.info("Received termination signal (%d). Shutting down...", signum)
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    server.start()


if __name__ == "__main__":
    main()
