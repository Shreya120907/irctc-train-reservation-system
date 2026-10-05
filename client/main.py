"""
Main Application Entry Point for IRCTC-Style Train Reservation Simulator
Coordinates QStackedWidget navigation, theme styles, network layer lifecycle,
and real-time UDP broadcast propagation to the UI.
"""

import os
import sys
from typing import Any, Dict, Optional

# Ensure package root is in sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget
)

from network.tcp_client import TCPClient
from network.udp_client import UDPClient
from network.http_client import HTTPClient

from ui.login import LoginWidget
from ui.register import RegisterWidget
from ui.dashboard import DashboardWidget
from ui.search import SearchWidget
from ui.seat_selection import SeatSelectionWidget
from ui.booking import BookingWidget
from ui.bookings import BookingsWidget
from ui.admin import AdminWidget


class MainWindow(QMainWindow):
    """
    Primary desktop window housing the QStackedWidget navigation engine,
    top branding bar, connection telemetry, and background UDP thread lifecycle.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("IRCTC Next-Gen RailConnect Desktop Simulator")
        self.resize(1180, 820)
        self.setMinimumSize(960, 680)

        # -------------------------------------------------------------
        # 1. Initialize Network Clients
        # -------------------------------------------------------------
        self.tcp_client = TCPClient(host="127.0.0.1", port=9000)
        self.http_client = HTTPClient(base_url="http://127.0.0.1:8000")
        self.udp_port = 9999
        self.udp_client = UDPClient(port=self.udp_port)

        # Connect UDP thread signals
        self.udp_client.announcement_received.connect(self._on_udp_announcement)
        self.udp_client.listener_status.connect(self._on_udp_status_changed)

        # Start background UDP thread
        self.udp_client.start()

        # Current user profile
        self.current_user: Optional[Dict[str, Any]] = None

        # -------------------------------------------------------------
        # 2. Build UI Layout
        # -------------------------------------------------------------
        self._init_ui()
        self._apply_global_styles()

        # Periodic health check timer (every 15s)
        self.health_timer = QTimer(self)
        self.health_timer.timeout.connect(self._poll_server_health)
        self.health_timer.start(15000)

    def _init_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Global Top Navigation / Header Bar
        self.nav_bar = self._create_top_bar()
        root_layout.addWidget(self.nav_bar)

        # Real-time Broadcast Ticker Bar
        self.ticker_bar = self._create_ticker_bar()
        root_layout.addWidget(self.ticker_bar)

        # Central Stacked Widget for Page Navigation
        self.stack = QStackedWidget(self)
        root_layout.addWidget(self.stack, 1)

        # -------------------------------------------------------------
        # 3. Instantiate and Register UI Views
        # -------------------------------------------------------------
        self.login_view = LoginWidget(self.tcp_client, self.http_client, default_udp_port=self.udp_port)
        self.register_view = RegisterWidget(self.tcp_client)
        self.dashboard_view = DashboardWidget(self.tcp_client, self.http_client)
        self.search_view = SearchWidget(self.tcp_client)
        self.seat_view = SeatSelectionWidget(self.tcp_client)
        self.booking_view = BookingWidget(self.tcp_client)
        self.bookings_view = BookingsWidget(self.tcp_client, self.http_client)
        self.admin_view = AdminWidget(self.tcp_client, self.http_client)

        # Add to stack
        self.stack.addWidget(self.login_view)        # Index 0
        self.stack.addWidget(self.register_view)     # Index 1
        self.stack.addWidget(self.dashboard_view)    # Index 2
        self.stack.addWidget(self.search_view)       # Index 3
        self.stack.addWidget(self.seat_view)         # Index 4
        self.stack.addWidget(self.booking_view)      # Index 5
        self.stack.addWidget(self.bookings_view)     # Index 6
        self.stack.addWidget(self.admin_view)        # Index 7

        # -------------------------------------------------------------
        # 4. Wire View Navigation Signals
        # -------------------------------------------------------------
        # Login wiring
        self.login_view.login_successful.connect(self._on_login_success)
        self.login_view.switch_to_register.connect(lambda: self._navigate_to("register"))
        self.login_view.connection_settings_changed.connect(self._on_settings_reconfigured)

        # Register wiring
        self.register_view.switch_to_login.connect(lambda: self._navigate_to("login"))
        self.register_view.registration_successful.connect(lambda res: self._navigate_to("login"))

        # Dashboard wiring
        self.dashboard_view.navigate_requested.connect(self._navigate_to)

        # Search wiring
        self.search_view.train_selected.connect(self._on_train_selected)
        self.search_view.back_requested.connect(lambda: self._navigate_to("dashboard"))

        # Seat Selection wiring
        self.seat_view.proceed_to_booking.connect(self._on_seats_confirmed)
        self.seat_view.back_requested.connect(lambda: self._navigate_to("search"))

        # Booking wiring
        self.booking_view.booking_completed.connect(self._on_booking_success)
        self.booking_view.back_requested.connect(lambda: self._navigate_to("seat_selection"))

        # Bookings & PNR wiring
        self.bookings_view.back_requested.connect(lambda: self._navigate_to("dashboard"))

        # Admin wiring
        self.admin_view.back_requested.connect(lambda: self._navigate_to("dashboard"))

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready. UDP Broadcast listener active.")

        # Initial state: Show Login view
        self._navigate_to("login")

    def _create_top_bar(self) -> QFrame:
        bar = QFrame(self)
        bar.setFixedHeight(54)
        bar.setStyleSheet("""
            QFrame {
                background-color: #0b3c68;
                border-bottom: 2px solid #d35400;
            }
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        # Logo and Title
        brand_label = QLabel("🚆 IRCTC RailConnect")
        brand_label.setStyleSheet("color: #ffffff; font-size: 16px; font-weight: 800; letter-spacing: 0.5px;")
        layout.addWidget(brand_label)

        # Navigation Links (Visible when logged in)
        self.nav_links_container = QWidget()
        links_layout = QHBoxLayout(self.nav_links_container)
        links_layout.setContentsMargins(16, 0, 0, 0)
        links_layout.setSpacing(10)

        self.btn_nav_dashboard = self._make_nav_link("Dashboard", lambda: self._navigate_to("dashboard"))
        self.btn_nav_search = self._make_nav_link("Book Trains", lambda: self._navigate_to("search"))
        self.btn_nav_bookings = self._make_nav_link("My Bookings", lambda: self._navigate_to("bookings"))
        self.btn_nav_admin = self._make_nav_link("Admin Console", lambda: self._navigate_to("admin"))

        links_layout.addWidget(self.btn_nav_dashboard)
        links_layout.addWidget(self.btn_nav_search)
        links_layout.addWidget(self.btn_nav_bookings)
        links_layout.addWidget(self.btn_nav_admin)
        self.btn_nav_admin.setVisible(False)

        layout.addWidget(self.nav_links_container)
        layout.addStretch()

        # Connection indicators
        self.conn_pill = QLabel("● TCP: Offline")
        self.conn_pill.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.15);
            color: #fca5a5;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: bold;
        """)
        layout.addWidget(self.conn_pill)

        # User profile / Logout
        self.user_session_lbl = QLabel("")
        self.user_session_lbl.setStyleSheet("color: #ffffff; font-weight: 600; font-size: 12px;")
        layout.addWidget(self.user_session_lbl)

        self.logout_btn = QPushButton("Logout")
        self.logout_btn.setCursor(Qt.PointingHandCursor)
        self.logout_btn.setStyleSheet("""
            QPushButton {
                background-color: #d35400;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 5px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #b94400; }
        """)
        self.logout_btn.clicked.connect(self._handle_logout)
        layout.addWidget(self.logout_btn)

        self.nav_links_container.setVisible(False)
        self.user_session_lbl.setVisible(False)
        self.logout_btn.setVisible(False)

        return bar

    def _make_nav_link(self, title: str, callback) -> QPushButton:
        btn = QPushButton(title)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background: none;
                border: none;
                color: #e2e8f0;
                font-weight: bold;
                font-size: 12px;
                padding: 6px 10px;
            }
            QPushButton:hover {
                color: #ffffff;
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 4px;
            }
        """)
        btn.clicked.connect(callback)
        return btn

    def _create_ticker_bar(self) -> QFrame:
        frame = QFrame(self)
        frame.setFixedHeight(28)
        frame.setStyleSheet("background-color: #fef3c7; border-bottom: 1px solid #fde68a;")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(16, 2, 16, 2)

        icon_lbl = QLabel("📢 LIVE ALERTS:")
        icon_lbl.setStyleSheet("color: #92400e; font-weight: 800; font-size: 10px;")
        layout.addWidget(icon_lbl)

        self.ticker_text = QLabel("Listening for real-time announcements from server over UDP broadcast...")
        self.ticker_text.setStyleSheet("color: #78350f; font-size: 11px; font-weight: 500;")
        layout.addWidget(self.ticker_text, 1)

        return frame

    def _apply_global_styles(self) -> None:
        """Sets cohesive desktop stylesheet for controls, tables, dialogs, and fonts."""
        font = QFont("Segoe UI", 10)
        self.setFont(font)
        self.setStyleSheet("""
            QWidget {
                background-color: #f8fafc;
                color: #1e293b;
            }
            QScrollBar:vertical {
                border: none;
                background: #f1f5f9;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #cbd5e1;
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #94a3b8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

    # =========================================================================
    # Navigation Controller
    # =========================================================================

    def _navigate_to(self, route: str) -> None:
        """Switches central stacked widget view."""
        route = route.lower()
        if route == "login":
            self.stack.setCurrentWidget(self.login_view)
            self._update_auth_header(False)
        elif route == "register":
            self.stack.setCurrentWidget(self.register_view)
            self._update_auth_header(False)
        elif route == "dashboard":
            self.stack.setCurrentWidget(self.dashboard_view)
            self._update_auth_header(True)
            self.dashboard_view.refresh_dashboard()
        elif route == "search":
            self.stack.setCurrentWidget(self.search_view)
            self._update_auth_header(True)
        elif route == "seat_selection":
            self.stack.setCurrentWidget(self.seat_view)
            self._update_auth_header(True)
        elif route == "booking":
            self.stack.setCurrentWidget(self.booking_view)
            self._update_auth_header(True)
        elif route == "bookings":
            self.stack.setCurrentWidget(self.bookings_view)
            self._update_auth_header(True)
            self.bookings_view.fetch_bookings()
        elif route == "admin":
            if self.current_user and self.current_user.get("role") == "admin":
                self.stack.setCurrentWidget(self.admin_view)
                self._update_auth_header(True)
                self.admin_view.refresh_all_admin_data()
            else:
                QMessageBox.warning(self, "Access Denied", "Administrative privileges required.")
        elif route == "logout":
            self._handle_logout()

    def _update_auth_header(self, is_authenticated: bool) -> None:
        """Toggles top bar buttons based on login state."""
        self.nav_links_container.setVisible(is_authenticated)
        self.user_session_lbl.setVisible(is_authenticated)
        self.logout_btn.setVisible(is_authenticated)

        if is_authenticated and self.current_user:
            username = self.current_user.get("username", "Passenger")
            role = self.current_user.get("role", "passenger")
            self.user_session_lbl.setText(f"👤 {username} ({role.upper()})")
            self.btn_nav_admin.setVisible(role == "admin")

    # =========================================================================
    # Navigation Transitions with Parameter Hand-offs
    # =========================================================================

    def _on_login_success(self, user_info: Dict[str, Any]) -> None:
        """Transitions from login to dashboard, passing authenticated context."""
        self.current_user = user_info
        self.dashboard_view.set_user_context(user_info)
        self.conn_pill.setText("● TCP: Connected")
        self.conn_pill.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.15);
            color: #86efac;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: bold;
        """)

        # If admin, land directly or offer dashboard
        if user_info.get("role") == "admin":
            self._navigate_to("admin")
        else:
            self._navigate_to("dashboard")

    def _on_train_selected(self, train_ctx: Dict[str, Any]) -> None:
        """Hands selected train context to Seat Selection screen."""
        self.seat_view.set_train_context(train_ctx)
        self._navigate_to("seat_selection")

    def _on_seats_confirmed(self, booking_draft: Dict[str, Any]) -> None:
        """Hands configured booking draft to Passenger Booking screen."""
        self.booking_view.set_booking_draft(booking_draft)
        self._navigate_to("booking")

    def _on_booking_success(self, response: Dict[str, Any]) -> None:
        """Transitions to My Bookings upon successful reservation."""
        self._navigate_to("bookings")

    def _handle_logout(self) -> None:
        """Clears local user context and returns to Login view."""
        self.tcp_client.logout()
        self.current_user = None
        self.login_view.reset_fields()
        self.conn_pill.setText("● TCP: Offline")
        self.conn_pill.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.15);
            color: #fca5a5;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: bold;
        """)
        self._navigate_to("login")

    # =========================================================================
    # Network Events & Background Telemetry
    # =========================================================================

    def _on_settings_reconfigured(self, tcp_host: str, tcp_port: int, http_url: str, udp_port: int) -> None:
        self.tcp_client.host = tcp_host
        self.tcp_client.port = tcp_port
        if hasattr(self.http_client, "set_base_url"):
            self.http_client.set_base_url(http_url)
        else:
            self.http_client.base_url = http_url

        # Check if UDP port was changed away from the active broadcast port (9999)
        if udp_port != 9999:
            self.udp_port = udp_port
            warning_text = f"⚠️ UDP Broadcast Not Available on Port {udp_port} (Expected: 9999)"
            
            # 1. Show immediate GUI Popup Dialog
            QMessageBox.warning(
                self,
                "UDP Service Unavailable",
                f"UDP broadcast port set to {udp_port}.\n\n"
                f"The server broadcasts announcements exclusively on port 9999.\n"
                f"Live broadcast notifications will remain unavailable until restored to 9999."
            )

            # 2. Update the persistent top Live Alerts banner
            if hasattr(self, "alert_banner"):
                self.alert_banner.setText(warning_text)
                self.alert_banner.setStyleSheet("background-color: #fee2e2; color: #dc2626; font-weight: bold; padding: 6px;")

            # 3. Add card to Dashboard live feed if initialized
            if hasattr(self, "dashboard_view"):
                self.dashboard_view.add_live_announcement({
                    "type": "UDP UNAVAILABLE",
                    "message": f"UDP listener bound to port {udp_port}. Real-time alerts unavailable (expected port: 9999)."
                })
        else:
            self.udp_port = udp_port
            if hasattr(self, "alert_banner"):
                self.alert_banner.setText("● Live Alerts: Listening for real-time announcements from server over UDP broadcast...")
                self.alert_banner.setStyleSheet("background-color: #fef3c7; color: #92400e; padding: 6px;")
                
        """Applies reconfigured network parameters and restarts UDP thread if port changed."""
        self.tcp_client.host = tcp_host
        self.tcp_client.port = tcp_port
        self.http_client.set_base_url(http_url)

        if udp_port != self.udp_port:
            self.udp_port = udp_port
            self.udp_client.stop()
            self.udp_client.configure(port=udp_port)
            self.udp_client.start()

    def _on_udp_announcement(self, data: Dict[str, Any]) -> None:
        """Handles real-time announcement received on background UDP socket."""
        msg = data.get("message", "New server announcement received.")
        t_type = data.get("type", "ALERT")
        time_str = data.get("timestamp", "")

        # Update top ticker
        self.ticker_text.setText(f"[{t_type}] {msg} ({time_str})")

        # Forward to dashboard feed
        self.dashboard_view.add_live_announcement(data)
        self.status_bar.showMessage(f"Broadcast: {msg}", 8000)

    def _on_udp_status_changed(self, is_active: bool, msg: str) -> None:
        self.status_bar.showMessage(msg, 5000)

    def _poll_server_health(self) -> None:
        """Periodic background pulse checking HTTP REST health."""
        res = self.http_client.check_health()
        if res.get("success"):
            self.status_bar.showMessage(f"Server Health: {res.get('status', 'OK')}", 3000)
        else:
            self.status_bar.showMessage("Server Health Check: Unreachable", 3000)

    # =========================================================================
    # Graceful Shutdown
    # =========================================================================

    def closeEvent(self, event: QCloseEvent) -> None:
        """Cleanly halts background threads and closes TCP socket."""
        self.health_timer.stop()
        if self.udp_client and self.udp_client.isRunning():
            self.udp_client.stop()
        if self.tcp_client:
            self.tcp_client.disconnect()
        event.accept()


def main():
    import os
    import sys
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    app.setStyleSheet("""
        * {
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 13px;
            color: #0f172a;
        }

        /* Top Navigation Bar tabs - high-contrast visible text */
        QTabBar::tab {
            background-color: transparent;
            color: #0f172a;
            font-size: 14px;
            font-weight: 700;
            padding: 12px 28px;
            min-height: 24px;
            border: 2px;
        }
        QTabBar::tab:selected {
            color: #0b3c68;
            background-color: rgba(11, 60, 104, 0.12);
            border-bottom: 4px solid #0b3c68;
        }
        QTabBar::tab:hover {
            background-color: rgba(0, 0, 0, 0.06);
            color: #000000;
        }

        /* Global buttons and inputs */
        QPushButton {
            min-height: 38px;
            border-radius: 6px;
            font-weight: 600;
        }
        QLineEdit, QComboBox {
            min-height: 38px;
            padding: 4px 10px;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            background-color: #ffffff;
            color: #0f172a;
        }

        /* Table & Card Headers */
        QHeaderView::section {
            background-color: #f1f5f9;
            color: #0f172a;
            font-weight: 700;
            padding: 6px;
            border: 1px solid #e2e8f0;
        }
        QTableWidget {
            font-size: 13px;
            color: #1e293b;
            gridline-color: #e2e8f0;
            background-color: #ffffff;
        }
    """)

    app.setApplicationName("IRCTC Train Reservation Simulator")
    app.setOrganizationName("IRCTC-Simulation")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


# Make sure these two lines are at the root level (no indentation)
if __name__ == "__main__":
    main()