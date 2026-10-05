"""
Registration View for IRCTC-Style Train Reservation Simulator
Handles passenger account onboarding with strict pre-flight validation and role assignment.
"""

import re
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget
)

try:
    from client.network.tcp_client import TCPClient
except (ImportError, ValueError):
    try:
        from ..network.tcp_client import TCPClient
    except (ImportError, ValueError):
        from network.tcp_client import TCPClient


class RegisterWidget(QWidget):
    """
    User registration screen with pre-flight regex validation and role assignment.
    """

    registration_successful = Signal(dict)
    switch_to_login = Signal()

    def __init__(self, tcp_client: TCPClient, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.tcp_client = tcp_client
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignCenter)
        main_layout.setContentsMargins(30, 20, 30, 20)

        # Container Card
        card = QFrame(self)
        card.setObjectName("cardFrame")
        card.setFixedWidth(500)
        card.setStyleSheet("""
            #cardFrame {
                background-color: #ffffff;
                border: 1px solid #dcdfe6;
                border-radius: 12px;
                padding: 24px;
            }
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(12)

        # Header
        header_layout = QVBoxLayout()
        header_layout.setAlignment(Qt.AlignCenter)

        badge_label = QLabel("🚆 CITIZEN ONBOARDING")
        badge_label.setAlignment(Qt.AlignCenter)
        badge_label.setStyleSheet("color: #d35400; font-size: 12px; font-weight: bold; letter-spacing: 2px;")
        header_layout.addWidget(badge_label)

        title_label = QLabel("Create IRCTC Account")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #0b3c68; font-size: 20px; font-weight: 800; margin-bottom: 2px;")
        header_layout.addWidget(title_label)

        sub_label = QLabel("Register for direct access to train search, booking & PNR tracking")
        sub_label.setAlignment(Qt.AlignCenter)
        sub_label.setStyleSheet("color: #64748b; font-size: 11px;")
        header_layout.addWidget(sub_label)

        card_layout.addLayout(header_layout)

        # Form Layout
        form_layout = QVBoxLayout()
        form_layout.setSpacing(8)

        # Full Name
        name_label = QLabel("Full Legal Name *")
        name_label.setStyleSheet("font-size: 11px; font-weight: 600; color: #1e293b;")
        self.fullname_input = QLineEdit()
        self.fullname_input.setPlaceholderText("e.g. Ramesh Kumar")
        self._style_input(self.fullname_input)
        form_layout.addWidget(name_label)
        form_layout.addWidget(self.fullname_input)

        # Username
        user_label = QLabel("Username / User ID *")
        user_label.setStyleSheet("font-size: 11px; font-weight: 600; color: #1e293b;")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("e.g. ramesh_k (minimum 3 characters)")
        self._style_input(self.username_input)
        form_layout.addWidget(user_label)
        form_layout.addWidget(self.username_input)

        # Email & Mobile (2-column layout)
        contact_row = QHBoxLayout()
        contact_row.setSpacing(10)

        email_col = QVBoxLayout()
        email_label = QLabel("Email Address *")
        email_label.setStyleSheet("font-size: 11px; font-weight: 600; color: #1e293b;")
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("name@domain.com")
        self._style_input(self.email_input)
        email_col.addWidget(email_label)
        email_col.addWidget(self.email_input)
        contact_row.addLayout(email_col)

        phone_col = QVBoxLayout()
        phone_label = QLabel("Mobile Number *")
        phone_label.setStyleSheet("font-size: 11px; font-weight: 600; color: #1e293b;")
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("10-digit mobile number")
        self.phone_input.setMaxLength(10)
        self._style_input(self.phone_input)
        phone_col.addWidget(phone_label)
        phone_col.addWidget(self.phone_input)
        contact_row.addLayout(phone_col)

        form_layout.addLayout(contact_row)

        # Password & Confirm Password (2-column layout)
        pass_row = QHBoxLayout()
        pass_row.setSpacing(10)

        p1_col = QVBoxLayout()
        p1_label = QLabel("Password *")
        p1_label.setStyleSheet("font-size: 11px; font-weight: 600; color: #1e293b;")
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.Password)
        self.pass_input.setPlaceholderText("Min. 6 chars")
        self._style_input(self.pass_input)
        p1_col.addWidget(p1_label)
        p1_col.addWidget(self.pass_input)
        pass_row.addLayout(p1_col)

        p2_col = QVBoxLayout()
        p2_label = QLabel("Confirm Password *")
        p2_label.setStyleSheet("font-size: 11px; font-weight: 600; color: #1e293b;")
        self.confirm_pass_input = QLineEdit()
        self.confirm_pass_input.setEchoMode(QLineEdit.Password)
        self.confirm_pass_input.setPlaceholderText("Re-type password")
        self._style_input(self.confirm_pass_input)
        p2_col.addWidget(p2_label)
        p2_col.addWidget(self.confirm_pass_input)
        pass_row.addLayout(p2_col)

        form_layout.addLayout(pass_row)

        # Role
        role_label = QLabel("Account Type / Role")
        role_label.setStyleSheet("font-size: 11px; font-weight: 600; color: #1e293b;")
        self.role_combo = QComboBox()
        self.role_combo.addItem("Passenger (Standard Citizen Account)", "passenger")
        self.role_combo.addItem("Station Admin / Operations Manager", "admin")
        self.role_combo.setStyleSheet("""
            QComboBox {
                padding: 6px 10px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
            }
        """)
        form_layout.addWidget(role_label)
        form_layout.addWidget(self.role_combo)

        card_layout.addLayout(form_layout)

        # Submit Button
        self.register_btn = QPushButton("Complete Registration")
        self.register_btn.setCursor(Qt.PointingHandCursor)
        self.register_btn.setStyleSheet("""
            QPushButton {
                background-color: #d35400;
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                padding: 10px;
                border-radius: 6px;
                margin-top: 6px;
            }
            QPushButton:hover { background-color: #b94400; }
            QPushButton:pressed { background-color: #9c3600; }
        """)
        self.register_btn.clicked.connect(self._handle_register)
        card_layout.addWidget(self.register_btn)

        # Back to Login
        back_row = QHBoxLayout()
        back_row.setAlignment(Qt.AlignCenter)
        back_text = QLabel("Already have an IRCTC account?")
        back_text.setStyleSheet("color: #64748b; font-size: 12px;")
        self.back_btn = QPushButton("Sign In")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setStyleSheet("""
            QPushButton {
                background: none;
                border: none;
                color: #0b3c68;
                font-weight: bold;
                font-size: 12px;
                text-decoration: underline;
            }
            QPushButton:hover { color: #082947; }
        """)
        self.back_btn.clicked.connect(self.switch_to_login.emit)
        back_row.addWidget(back_text)
        back_row.addWidget(self.back_btn)
        card_layout.addLayout(back_row)

        main_layout.addWidget(card)

    def _style_input(self, widget: QLineEdit) -> None:
        widget.setStyleSheet("""
            QLineEdit {
                padding: 7px 10px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 12px;
            }
            QLineEdit:focus { border: 1px solid #0b3c68; }
        """)

    def _handle_register(self) -> None:
        """Performs comprehensive pre-flight validations and dispatches network registration."""
        full_name = self.fullname_input.text().strip()
        username = self.username_input.text().strip()
        email = self.email_input.text().strip()
        phone = self.phone_input.text().strip()
        password = self.pass_input.text()
        confirm_pass = self.confirm_pass_input.text()
        role = self.role_combo.currentData()

        # Pre-flight field presence
        if not full_name:
            QMessageBox.warning(self, "Validation Error", "Full Legal Name is required.")
            self.fullname_input.setFocus()
            return

        if not username or len(username) < 3:
            QMessageBox.warning(self, "Validation Error", "Username must be at least 3 characters long.")
            self.username_input.setFocus()
            return

        if not re.match(r"^[a-zA-Z0-9_.-]+$", username):
            QMessageBox.warning(
                self,
                "Validation Error",
                "Username may only contain letters, numbers, underscores, and hyphens."
            )
            self.username_input.setFocus()
            return

        # Email regex check
        email_pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not email or not re.match(email_pattern, email):
            QMessageBox.warning(
                self,
                "Validation Error",
                "Please enter a valid email address (e.g. name@domain.com)."
            )
            self.email_input.setFocus()
            return

        # Mobile number check
        if not phone or not phone.isdigit() or len(phone) != 10:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Please provide a valid 10-digit mobile number."
            )
            self.phone_input.setFocus()
            return

        # Password rules
        if not password or len(password) < 6:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Password must be at least 6 characters long."
            )
            self.pass_input.setFocus()
            return

        if password != confirm_pass:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Passwords do not match. Please re-enter carefully."
            )
            self.confirm_pass_input.setFocus()
            return

        self.register_btn.setEnabled(False)
        self.register_btn.setText("Registering...")

        try:
            response = self.tcp_client.register(
                username=username,
                password=password,
                email=email,
                full_name=full_name,
                phone=phone,
                role=role
            )

            if response.get("success"):
                QMessageBox.information(
                    self,
                    "Registration Successful",
                    f"Account for '{username}' created successfully! You can now log in."
                )
                self.registration_successful.emit(response)
                self.switch_to_login.emit()
            else:
                msg = response.get("message", "Registration failed. Username or email may already be in use.")
                QMessageBox.critical(self, "Registration Error", msg)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Network Error",
                f"Failed to communicate with registration server: {str(e)}"
            )
        finally:
            self.register_btn.setEnabled(True)
            self.register_btn.setText("Complete Registration")
