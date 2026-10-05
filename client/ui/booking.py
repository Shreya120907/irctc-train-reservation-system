"""
Booking View for IRCTC-Style Train Reservation Simulator
Handles passenger roster input, pre-flight contact validation,
confirmation dialogs, and atomic ticket reservation transactions via TCP.
"""

import re
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
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


class BookingWidget(QWidget):
    """
    Passenger details entry, fare computation, confirmation dialog,
    and atomic transaction processing.
    """

    booking_completed = Signal(dict)
    back_requested = Signal()

    def __init__(self, tcp_client: TCPClient, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.tcp_client = tcp_client

        self.booking_draft: Dict[str, Any] = {}
        self.passenger_widgets: List[Dict[str, Any]] = []

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # -------------------------------------------------------------
        # 1. Navigation Header
        # -------------------------------------------------------------
        nav_row = QHBoxLayout()
        self.back_btn = QPushButton("← Back to Seat Selection")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setStyleSheet("""
            QPushButton {
                background: none;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 6px 12px;
                color: #0b3c68;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #f1f5f9; }
        """)
        self.back_btn.clicked.connect(self.back_requested.emit)
        nav_row.addWidget(self.back_btn)

        nav_row.addStretch()

        title = QLabel("Passenger Details & Ticket Confirmation")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #0b3c68;")
        nav_row.addWidget(title)

        nav_row.addStretch()
        main_layout.addLayout(nav_row)

        # -------------------------------------------------------------
        # 2. Main Content Split: Form & Order Summary
        # -------------------------------------------------------------
        content_layout = QHBoxLayout()
        content_layout.setSpacing(16)

        # Left Column: Passenger Cards Form
        left_col = QVBoxLayout()

        # Journey Info Card
        self.journey_card = QFrame()
        self.journey_card.setStyleSheet("""
            QFrame {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-left: 4px solid #0b3c68;
                border-radius: 6px;
                padding: 12px;
            }
        """)
        self.journey_layout = QVBoxLayout(self.journey_card)
        self.journey_summary_label = QLabel("No journey loaded.")
        self.journey_summary_label.setStyleSheet("font-weight: bold; color: #1e293b; font-size: 13px;")
        self.journey_details_label = QLabel("")
        self.journey_details_label.setStyleSheet("color: #64748b; font-size: 11px;")
        self.journey_layout.addWidget(self.journey_summary_label)
        self.journey_layout.addWidget(self.journey_details_label)
        left_col.addWidget(self.journey_card)

        # Passenger Roster Scroll Area
        roster_card = QFrame()
        roster_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 14px;
            }
        """)
        roster_layout = QVBoxLayout(roster_card)

        roster_header = QHBoxLayout()
        r_title = QLabel("Passenger Information")
        r_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #0b3c68;")
        roster_header.addWidget(r_title)
        roster_header.addStretch()
        roster_layout.addLayout(roster_header)

        self.passengers_scroll = QScrollArea()
        self.passengers_scroll.setWidgetResizable(True)
        self.passengers_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.passengers_container = QWidget()
        self.passengers_layout = QVBoxLayout(self.passengers_container)
        self.passengers_layout.setSpacing(10)
        self.passengers_scroll.setWidget(self.passengers_container)

        roster_layout.addWidget(self.passengers_scroll)
        left_col.addWidget(roster_card, 1)

        # Contact Details Card
        contact_card = QFrame()
        contact_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        contact_layout = QVBoxLayout(contact_card)
        c_title = QLabel("Contact for e-Ticket & SMS Alerts")
        c_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #0b3c68;")
        contact_layout.addWidget(c_title)

        contact_inputs = QHBoxLayout()
        c_phone_col = QVBoxLayout()
        c_phone_lbl = QLabel("Mobile Number *")
        c_phone_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #334155;")
        self.contact_phone = QLineEdit()
        self.contact_phone.setPlaceholderText("10-digit mobile number")
        self.contact_phone.setMaxLength(10)
        self._style_input(self.contact_phone)
        c_phone_col.addWidget(c_phone_lbl)
        c_phone_col.addWidget(self.contact_phone)
        contact_inputs.addLayout(c_phone_col)

        c_email_col = QVBoxLayout()
        c_email_lbl = QLabel("Email Address *")
        c_email_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #334155;")
        self.contact_email = QLineEdit()
        self.contact_email.setPlaceholderText("name@domain.com")
        self._style_input(self.contact_email)
        c_email_col.addWidget(c_email_lbl)
        c_email_col.addWidget(self.contact_email)
        contact_inputs.addLayout(c_email_col)

        contact_layout.addLayout(contact_inputs)
        left_col.addWidget(contact_card)

        content_layout.addLayout(left_col, 2)

        # Right Column: Fare Breakdown, Payment Gateway & Confirmation
        right_col = QVBoxLayout()

        fare_card = QFrame()
        fare_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 16px;
            }
        """)
        fare_layout = QVBoxLayout(fare_card)
        fare_layout.setSpacing(12)

        f_title = QLabel("Fare & Payment Breakdown")
        f_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #0b3c68;")
        fare_layout.addWidget(f_title)

        # Breakdown items
        self.lbl_base_fare = QLabel("Ticket Base Fare: ₹ 0.00")
        self.lbl_reservation_fee = QLabel("Reservation / Superfast Charges: ₹ 40.00")
        self.lbl_gst = QLabel("GST (5%): ₹ 0.00")
        self.lbl_total_fare = QLabel("Total Amount: ₹ 0.00")
        self.lbl_total_fare.setStyleSheet("font-size: 16px; font-weight: 800; color: #d35400; padding-top: 6px;")

        fare_layout.addWidget(self.lbl_base_fare)
        fare_layout.addWidget(self.lbl_reservation_fee)
        fare_layout.addWidget(self.lbl_gst)
        fare_layout.addWidget(self.lbl_total_fare)

        # Payment Mode Selection
        p_mode_lbl = QLabel("Select Payment Gateway:")
        p_mode_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #334155; margin-top: 10px;")
        fare_layout.addWidget(p_mode_lbl)

        self.payment_combo = QComboBox()
        self.payment_combo.addItems([
            "IRCTC iPay (UPI, QR, Cards, NetBanking)",
            "Rail Wallet / Instant Pay",
            "State Bank of India Multi-Option Payment (MOPS)",
            "PayTM / Google Pay Instant Gateway"
        ])
        self.payment_combo.setStyleSheet("padding: 6px; border: 1px solid #cbd5e1; border-radius: 4px;")
        fare_layout.addWidget(self.payment_combo)

        # Atomic Booking Button
        self.pay_book_btn = QPushButton("Book & Pay Now")
        self.pay_book_btn.setCursor(Qt.PointingHandCursor)
        self.pay_book_btn.setStyleSheet("""
            QPushButton {
                background-color: #d35400;
                color: #ffffff;
                font-size: 14px;
                font-weight: bold;
                padding: 12px;
                border-radius: 6px;
                margin-top: 10px;
            }
            QPushButton:hover { background-color: #b94400; }
            QPushButton:pressed { background-color: #9c3600; }
        """)
        self.pay_book_btn.clicked.connect(self._handle_booking_submission)
        fare_layout.addWidget(self.pay_book_btn)

        right_col.addWidget(fare_card)
        right_col.addStretch()

        content_layout.addLayout(right_col, 1)
        main_layout.addLayout(content_layout)

    def _style_input(self, widget: QLineEdit) -> None:
        widget.setStyleSheet("""
            QLineEdit {
                padding: 6px 8px;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                font-size: 12px;
            }
            QLineEdit:focus { border: 1px solid #0b3c68; }
        """)

    def set_booking_draft(self, draft: Dict[str, Any]) -> None:
        """Sets up journey data, generates passenger input cards, and calculates fare."""
        self.booking_draft = draft
        train_ctx = draft.get("train_context", {})
        train = train_ctx.get("train", {})

        train_no = train.get("train_number", train.get("number", "N/A"))
        train_name = train.get("train_name", train.get("name", "Express"))
        date = train_ctx.get("date", "")
        src = train_ctx.get("source", train.get("source", ""))
        dst = train_ctx.get("destination", train.get("destination", ""))
        coach_class = draft.get("coach_class", "SL")
        quota = train_ctx.get("quota", "GENERAL")
        selected_seats = draft.get("selected_seats", [])

        self.journey_summary_label.setText(f"{train_no} - {train_name} | Class: {coach_class} ({quota})")
        self.journey_details_label.setText(
            f"Route: {src} → {dst} | Journey Date: {date} | Assigned Seats: {', '.join(selected_seats)}"
        )

        # Pre-fill user contact info if available in session
        if self.tcp_client.current_user:
            user = self.tcp_client.current_user
            if not self.contact_email.text():
                self.contact_email.setText(user.get("email", ""))
            if not self.contact_phone.text():
                self.contact_phone.setText(user.get("phone", ""))

        # Build passenger cards
        self._build_passenger_cards(selected_seats)

        # Compute Fares
        base_fare_rate = float(draft.get("base_fare", 450.0))
        seat_count = len(selected_seats)
        subtotal = base_fare_rate * seat_count
        reservation_charge = 40.0 * seat_count
        gst = (subtotal + reservation_charge) * 0.05
        grand_total = subtotal + reservation_charge + gst

        self.booking_draft["grand_total"] = grand_total
        self.lbl_base_fare.setText(f"Ticket Base Fare: ₹ {subtotal:.2f}")
        self.lbl_reservation_fee.setText(f"Reservation / Superfast Charges: ₹ {reservation_charge:.2f}")
        self.lbl_gst.setText(f"GST (5%): ₹ {gst:.2f}")
        self.lbl_total_fare.setText(f"Total Amount: ₹ {grand_total:.2f}")

    def _build_passenger_cards(self, seats: List[str]) -> None:
        """Dynamically generates passenger input rows matching selected seats."""
        # Clear existing passenger cards
        while self.passengers_layout.count():
            item = self.passengers_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.passenger_widgets.clear()

        for idx, seat_num in enumerate(seats):
            card = QFrame()
            card.setStyleSheet("""
                QFrame {
                    background-color: #f8fafc;
                    border: 1px solid #e2e8f0;
                    border-radius: 6px;
                    padding: 8px;
                }
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setSpacing(6)

            title_row = QHBoxLayout()
            p_label = QLabel(f"Passenger {idx + 1}")
            p_label.setStyleSheet("font-weight: bold; font-size: 11px; color: #0b3c68;")
            seat_badge = QLabel(f"Seat #{seat_num}")
            seat_badge.setStyleSheet("""
                background-color: #e0f2fe;
                color: #0369a1;
                font-weight: bold;
                font-size: 10px;
                padding: 2px 6px;
                border-radius: 3px;
            """)
            title_row.addWidget(p_label)
            title_row.addWidget(seat_badge)
            title_row.addStretch()
            card_layout.addLayout(title_row)

            fields_row = QHBoxLayout()
            fields_row.setSpacing(8)

            name_input = QLineEdit()
            name_input.setPlaceholderText("Passenger Full Name *")
            self._style_input(name_input)
            fields_row.addWidget(name_input, 3)

            age_input = QSpinBox()
            age_input.setRange(1, 120)
            age_input.setValue(28)
            age_input.setSuffix(" yrs")
            age_input.setStyleSheet("padding: 5px; border: 1px solid #cbd5e1; border-radius: 4px;")
            fields_row.addWidget(age_input, 1)

            gender_combo = QComboBox()
            gender_combo.addItems(["Male", "Female", "Transgender"])
            gender_combo.setStyleSheet("padding: 5px; border: 1px solid #cbd5e1; border-radius: 4px;")
            fields_row.addWidget(gender_combo, 1)

            berth_combo = QComboBox()
            berth_combo.addItems([
                "No Preference", "Lower Berth", "Middle Berth", "Upper Berth",
                "Side Lower", "Side Upper"
            ])
            berth_combo.setStyleSheet("padding: 5px; border: 1px solid #cbd5e1; border-radius: 4px;")
            fields_row.addWidget(berth_combo, 2)

            senior_check = QCheckBox("Sr. Citizen")
            senior_check.setStyleSheet("font-size: 11px; color: #475569;")
            fields_row.addWidget(senior_check)

            card_layout.addLayout(fields_row)
            self.passengers_layout.addWidget(card)

            self.passenger_widgets.append({
                "seat": seat_num,
                "name": name_input,
                "age": age_input,
                "gender": gender_combo,
                "berth_pref": berth_combo,
                "senior": senior_check
            })

    def _handle_booking_submission(self) -> None:
        """Validates inputs, presents confirmation modal, and triggers atomic booking."""
        # 1. Contact Validation
        phone = self.contact_phone.text().strip()
        email = self.contact_email.text().strip()

        if not phone or not phone.isdigit() or len(phone) != 10:
            QMessageBox.warning(self, "Validation Error", "Please provide a valid 10-digit mobile number for ticket alerts.")
            self.contact_phone.setFocus()
            return

        email_pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not email or not re.match(email_pattern, email):
            QMessageBox.warning(self, "Validation Error", "Please provide a valid email address for e-Ticket delivery.")
            self.contact_email.setFocus()
            return

        # 2. Passenger Roster Validation
        passengers_data = []
        for idx, pw in enumerate(self.passenger_widgets):
            p_name = pw["name"].text().strip()
            if not p_name:
                QMessageBox.warning(
                    self,
                    "Validation Error",
                    f"Please enter the legal name for Passenger #{idx + 1}."
                )
                pw["name"].setFocus()
                return

            passengers_data.append({
                "name": p_name,
                "age": pw["age"].value(),
                "gender": pw["gender"].currentText(),
                "berth_preference": pw["berth_pref"].currentText(),
                "senior_citizen": pw["senior"].isChecked(),
                "seat_number": pw["seat"]
            })

        # 3. Confirmation Dialog (Required by PRD)
        train_ctx = self.booking_draft.get("train_context", {})
        train = train_ctx.get("train", {})
        train_no = train.get("train_number", train.get("number", "N/A"))
        train_name = train.get("train_name", train.get("name", "Express"))
        date = train_ctx.get("date", "")
        grand_total = self.booking_draft.get("grand_total", 0.0)

        confirm_msg = (
            f"Are you sure you want to proceed with this booking?\n\n"
            f"🚆 Train: {train_no} - {train_name}\n"
            f"📅 Date: {date}\n"
            f"👥 Passengers: {len(passengers_data)}\n"
            f"💺 Seats: {', '.join(self.booking_draft.get('selected_seats', []))}\n"
            f"💳 Total Amount Payable: ₹ {grand_total:.2f}\n\n"
            f"An atomic transaction will be executed with the reservation server."
        )

        reply = QMessageBox.question(
            self,
            "Confirm Train Ticket Booking",
            confirm_msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply != QMessageBox.Yes:
            return

        # 4. Atomic Network Transaction via TCP Client
        payload = {
            "train_id": train.get("train_number") or train.get("id"),
            "train_number": train.get("train_number"),
            "train_name": train.get("train_name"),
            "source": train_ctx.get("source"),
            "destination": train_ctx.get("destination"),
            "journey_date": date,
            "date": date,
            "coach_class": self.booking_draft.get("coach_class"),
            "quota": train_ctx.get("quota", "GENERAL"),
            "passengers": passengers_data,
            "seats": self.booking_draft.get("selected_seats", []),
            "total_fare": grand_total,
            "contact_phone": phone,
            "contact_email": email,
            "payment_gateway": self.payment_combo.currentText()
        }

        self.pay_book_btn.setEnabled(False)
        self.pay_book_btn.setText("Processing Atomic Reservation...")

        try:
            resp = self.tcp_client.book_ticket(payload)
            if resp.get("success"):
                pnr = resp.get("pnr", "PNR-SUCCESS")
                status = resp.get("status", "CONFIRMED")
                success_text = (
                    f"✓ Reservation Successful!\n\n"
                    f"PNR Number: {pnr}\n"
                    f"Status: {status}\n"
                    f"Tickets have been dispatched to {email} and SMS sent to {phone}."
                )
                QMessageBox.information(self, "Booking Confirmed", success_text)
                self.booking_completed.emit(resp)
            else:
                err = resp.get("message", "Booking transaction failed. Selected seats may have expired or been taken.")
                QMessageBox.critical(self, "Transaction Failed", err)
        except Exception as e:
            QMessageBox.critical(self, "Communication Failure", f"Transaction could not be completed: {str(e)}")
        finally:
            self.pay_book_btn.setEnabled(True)
            self.pay_book_btn.setText("Book & Pay Now")
