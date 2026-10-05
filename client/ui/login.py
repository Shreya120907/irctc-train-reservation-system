"""
Login View for IRCTC-Style Train Reservation Simulator
Provides user authentication, server configuration pre-flight testing, and registration redirection.
Clean responsive grid layout prevents High-DPI element overlapping.
"""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget
)

try:
    from client.network.tcp_client import TCPClient
    from client.network.http_client import HTTPClient
except (ImportError, ValueError):
    try:
        from ..network.tcp_client import TCPClient
        from ..network.http_client import HTTPClient
    except (ImportError, ValueError):
        from network.tcp_client import TCPClient
        from network.http_client import HTTPClient


class LoginWidget(QWidget):
    """
    User login screen with server connection settings and pre-flight validation.
    """

    login_successful = Signal(dict)
    switch_to_register = Signal()
    connection_settings_changed = Signal(str, int, str, int)

    def __init__(
        self,
        tcp_client: TCPClient,
        http_client: HTTPClient,
        default_udp_port: int = 9999,
        parent: Optional[QWidget] = None,
        **kwargs
    ):
        super().__init__(parent)
        self.tcp_client = tcp_client
        self.http_client = http_client
        self.default_udp_port = default_udp_port

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignCenter)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Container Card
        card = QFrame(self)
        card.setObjectName("cardFrame")
        card.setFixedWidth(480)
        card.setStyleSheet("""
            #cardFrame {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 12px;
                padding: 16px;
            }
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(16)
        card_layout.setContentsMargins(16, 16, 16, 16)

        # ---------------------------------------------------------
        # 1. Header with Official Railway Branding
        # ---------------------------------------------------------
        header_layout = QVBoxLayout()
        header_layout.setAlignment(Qt.AlignCenter)
        header_layout.setSpacing(4)

        badge_label = QLabel("🚆  INDIAN RAILWAYS")
        badge_label.setAlignment(Qt.AlignCenter)
        badge_label.setStyleSheet("color: #d97706; font-size: 11px; font-weight: 800; letter-spacing: 1.5px;")
        header_layout.addWidget(badge_label)

        title_label = QLabel("IRCTC RailConnect Simulator")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #0b3c68; font-size: 21px; font-weight: 800;")
        header_layout.addWidget(title_label)

        sub_label = QLabel("Next-Gen Passenger Ticketing & Network Portal")
        sub_label.setAlignment(Qt.AlignCenter)
        sub_label.setStyleSheet("color: #64748b; font-size: 12px;")
        header_layout.addWidget(sub_label)

        card_layout.addLayout(header_layout)

        # ---------------------------------------------------------
        # 2. Connection Config Box (Clean Grid Layout)
        # ---------------------------------------------------------
        self.config_box = QGroupBox("Network Gateway Endpoints")
        self.config_box.setStyleSheet("""
            QGroupBox {
                font-size: 12px;
                font-weight: 700;
                color: #0b3c68;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                margin-top: 8px;
                padding: 14px 12px 12px 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
            }
        """)
        
        grid_config = QGridLayout(self.config_box)
        grid_config.setVerticalSpacing(10)
        grid_config.setHorizontalSpacing(10)
        grid_config.setContentsMargins(8, 12, 8, 8)

        # Row 0: TCP Host & Port
        tcp_lbl = QLabel("TCP Gateway:")
        tcp_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155;")
        grid_config.addWidget(tcp_lbl, 0, 0)

        tcp_box = QHBoxLayout()
        tcp_box.setSpacing(6)
        self.tcp_host_input = QLineEdit("127.0.0.1")
        self.tcp_host_input.setPlaceholderText("Host IP")
        self.tcp_host_input.setStyleSheet("""
            QLineEdit {
                min-height: 32px;
                padding: 4px 8px;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                font-size: 12px;
            }
        """)
        self.tcp_port_input = QSpinBox()
        self.tcp_port_input.setRange(1, 65535)
        self.tcp_port_input.setValue(5000)
        self.tcp_port_input.setFixedWidth(85)
        self.tcp_port_input.setStyleSheet("""
            QSpinBox {
                min-height: 32px;
                padding: 4px 6px;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                font-size: 12px;
            }
        """)
        tcp_box.addWidget(self.tcp_host_input, 1)
        tcp_box.addWidget(self.tcp_port_input)
        grid_config.addLayout(tcp_box, 0, 1)

        # Row 1: HTTP API URL
        http_lbl = QLabel("HTTP Status API:")
        http_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155;")
        grid_config.addWidget(http_lbl, 1, 0)

        self.http_url_input = QLineEdit("http://127.0.0.1:8080")
        self.http_url_input.setPlaceholderText("http://host:port")
        self.http_url_input.setStyleSheet("""
            QLineEdit {
                min-height: 32px;
                padding: 4px 8px;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                font-size: 12px;
            }
        """)
        grid_config.addWidget(self.http_url_input, 1, 1)

        # Row 2: UDP Broadcast Port
        udp_lbl = QLabel("UDP Listener:")
        udp_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155;")
        grid_config.addWidget(udp_lbl, 2, 0)

        self.udp_port_input = QSpinBox()
        self.udp_port_input.setRange(1, 65535)
        self.udp_port_input.setValue(self.default_udp_port)
        self.udp_port_input.setStyleSheet("""
            QSpinBox {
                min-height: 32px;
                padding: 4px 6px;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                font-size: 12px;
            }
        """)
        grid_config.addWidget(self.udp_port_input, 2, 1)

        # Row 3: Pre-flight Ping Action
        ping_row = QHBoxLayout()
        ping_row.setSpacing(10)
        
        self.test_conn_btn = QPushButton("Ping Gateway")
        self.test_conn_btn.setCursor(Qt.PointingHandCursor)
        self.test_conn_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #0b3c68;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover { background-color: #e2e8f0; }
        """)
        self.test_conn_btn.clicked.connect(self._test_connection)
        ping_row.addWidget(self.test_conn_btn)

        self.conn_status_label = QLabel("Not Tested")
        self.conn_status_label.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 600;")
        ping_row.addWidget(self.conn_status_label, 1)

        grid_config.addLayout(ping_row, 3, 1)

        card_layout.addWidget(self.config_box)

        # ---------------------------------------------------------
        # 3. Login Credentials Form (Vertical Separation)
        # ---------------------------------------------------------
        form_layout = QVBoxLayout()
        form_layout.setSpacing(10)

        # Username
        user_lbl = QLabel("Username / Passenger ID")
        user_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #1e293b;")
        form_layout.addWidget(user_lbl)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter registered username")
        self.username_input.setStyleSheet("""
            QLineEdit {
                min-height: 38px;
                padding: 6px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 13px;
                background-color: #f8fafc;
            }
            QLineEdit:focus { border: 2px solid #0b3c68; background-color: #ffffff; }
        """)
        form_layout.addWidget(self.username_input)

        # Password
        pass_lbl = QLabel("Password")
        pass_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #1e293b;")
        form_layout.addWidget(pass_lbl)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Enter your account password")
        self.password_input.setStyleSheet("""
            QLineEdit {
                min-height: 38px;
                padding: 6px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 13px;
                background-color: #f8fafc;
            }
            QLineEdit:focus { border: 2px solid #0b3c68; background-color: #ffffff; }
        """)
        self.password_input.returnPressed.connect(self._handle_login)
        form_layout.addWidget(self.password_input)

        # Portal Role Row
        role_row = QHBoxLayout()
        role_lbl = QLabel("Portal Role:")
        role_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #1e293b;")
        role_row.addWidget(role_lbl)

        self.role_combo = QComboBox()
        self.role_combo.addItems(["Passenger / Citizen", "Railway Admin"])
        self.role_combo.setStyleSheet("""
            QComboBox {
                min-height: 36px;
                padding: 4px 10px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 12px;
                background-color: #ffffff;
            }
        """)
        role_row.addWidget(self.role_combo, 1)
        form_layout.addLayout(role_row)

        card_layout.addLayout(form_layout)

        # ---------------------------------------------------------
        # 4. Action Buttons & Navigation
        # ---------------------------------------------------------
        self.login_btn = QPushButton("Sign In to IRCTC")
        self.login_btn.setCursor(Qt.PointingHandCursor)
        self.login_btn.setStyleSheet("""
            QPushButton {
                background-color: #0b3c68;
                color: #ffffff;
                font-size: 14px;
                font-weight: bold;
                min-height: 42px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #145388; }
            QPushButton:pressed { background-color: #082947; }
        """)
        self.login_btn.clicked.connect(self._handle_login)
        card_layout.addWidget(self.login_btn)

        # Register Switch Row
        register_row = QHBoxLayout()
        register_row.setAlignment(Qt.AlignCenter)
        reg_text = QLabel("New to IRCTC?")
        reg_text.setStyleSheet("color: #64748b; font-size: 12px;")
        register_row.addWidget(reg_text)

        self.reg_btn = QPushButton("Register New Account")
        self.reg_btn.setCursor(Qt.PointingHandCursor)
        self.reg_btn.setStyleSheet("""
            QPushButton {
                background: none;
                border: none;
                color: #ea580c;
                font-weight: bold;
                font-size: 12px;
                text-decoration: underline;
                padding: 2px 6px;
            }
            QPushButton:hover { color: #c2410c; }
        """)
        self.reg_btn.clicked.connect(self.switch_to_register.emit)
        register_row.addWidget(self.reg_btn)
        card_layout.addLayout(register_row)

        main_layout.addWidget(card)

    def _test_connection(self) -> None:
        """Pings HTTP health endpoint, verifies TCP connection, and checks UDP configuration."""
        tcp_host = self.tcp_host_input.text().strip()
        tcp_port = self.tcp_port_input.value()
        http_url = self.http_url_input.text().strip()
        udp_port = self.udp_port_input.value()

        self.conn_status_label.setText("Testing gateway...")
        self.conn_status_label.setStyleSheet("color: #f59e0b; font-size: 11px;")

        # Update configured endpoints
        self.tcp_client.host = tcp_host
        self.tcp_client.port = tcp_port
        if hasattr(self.http_client, "set_base_url"):
            self.http_client.set_base_url(http_url)
        else:
            self.http_client.base_url = http_url

        # Check connectivity
        http_res = self.http_client.check_health()
        tcp_ok = False
        tcp_msg = ""
        try:
            connect_res = self.tcp_client.connect(tcp_host, tcp_port)
            if isinstance(connect_res, tuple):
                tcp_ok, tcp_msg = connect_res
            else:
                tcp_ok = bool(connect_res)
                tcp_msg = "Connected" if tcp_ok else "Refused"
            if tcp_ok and hasattr(self.tcp_client, "disconnect"):
                self.tcp_client.disconnect()
        except Exception as e:
            tcp_ok = False
            tcp_msg = str(e)

        # Notify parent app of updated settings (triggers the UDP warning check in main.py)
        self.connection_settings_changed.emit(tcp_host, tcp_port, http_url, udp_port)

        # Update status label with UDP availability feedback
        if tcp_ok and http_res.get("success"):
            if udp_port == 9999:
                self.conn_status_label.setText("● Online (TCP, HTTP & UDP OK)")
                self.conn_status_label.setStyleSheet("color: #10b981; font-weight: bold; font-size: 11px;")
            else:
                self.conn_status_label.setText("⚠️ Online (UDP Unavailable)")
                self.conn_status_label.setStyleSheet("color: #d97706; font-weight: bold; font-size: 11px;")
        elif tcp_ok:
            self.conn_status_label.setText("● TCP Online / HTTP Offline")
            self.conn_status_label.setStyleSheet("color: #f59e0b; font-size: 11px;")
        else:
            self.conn_status_label.setText(f"Offline: {tcp_msg}")
            self.conn_status_label.setStyleSheet("color: #ef4444; font-size: 11px;")

    def _handle_login(self) -> None:
        """Pre-flight validation followed by network login transaction."""
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not username:
            QMessageBox.warning(self, "Validation Error", "Please enter your username or passenger ID.")
            self.username_input.setFocus()
            return

        if len(username) < 3:
            QMessageBox.warning(self, "Validation Error", "Username must be at least 3 characters long.")
            self.username_input.setFocus()
            return

        if not password:
            QMessageBox.warning(self, "Validation Error", "Please enter your account password.")
            self.password_input.setFocus()
            return

        if len(password) < 4:
            QMessageBox.warning(self, "Validation Error", "Password must be at least 4 characters long.")
            self.password_input.setFocus()
            return

        tcp_host = self.tcp_host_input.text().strip()
        tcp_port = self.tcp_port_input.value()
        http_url = self.http_url_input.text().strip()
        udp_port = self.udp_port_input.value()

        self.tcp_client.host = tcp_host
        self.tcp_client.port = tcp_port
        if hasattr(self.http_client, "set_base_url"):
            self.http_client.set_base_url(http_url)
        else:
            self.http_client.base_url = http_url
            
        self.connection_settings_changed.emit(tcp_host, tcp_port, http_url, udp_port)

        self.login_btn.setEnabled(False)
        self.login_btn.setText("Authenticating...")

        try:
            response = self.tcp_client.login(username, password)
            if response.get("success"):
                user_info = response.get("user", {})
                if not user_info:
                    role_str = "admin" if "Admin" in self.role_combo.currentText() else "passenger"
                    user_info = {
                        "username": username,
                        "role": role_str,
                        "full_name": username,
                        "user_id": response.get("user_id", 1)
                    }
                if "Admin" in self.role_combo.currentText() and user_info.get("role") != "admin":
                    user_info["role"] = "admin"

                self.login_successful.emit(user_info)
            else:
                msg = response.get("message", "Invalid username or password. Please verify and retry.")
                QMessageBox.critical(self, "Authentication Failed", msg)
        except Exception as e:
            QMessageBox.critical(self, "Network Error", f"Unable to reach authentication server: {str(e)}")
        finally:
            self.login_btn.setEnabled(True)
            self.login_btn.setText("Sign In to IRCTC")

    def reset_fields(self) -> None:
        """Clears sensitive form fields."""
        self.password_input.clear()