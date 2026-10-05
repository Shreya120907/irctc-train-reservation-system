"""
Bookings & PNR Tracking View for IRCTC-Style Train Reservation Simulator
Provides user booking management, cancellation with confirmation dialogs,
live PNR status lookup, and HTTP REST train running tracker.
Zero hardcoded data: all tables and status cards hydrate solely from network calls.
"""

from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
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


class BookingsWidget(QWidget):
    """
    My Bookings manager with cancellation workflow, PNR tracking, and live train status.
    """

    back_requested = Signal()

    def __init__(
        self,
        tcp_client: TCPClient,
        http_client: HTTPClient,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.tcp_client = tcp_client
        self.http_client = http_client
        self._bookings_cache: List[Dict[str, Any]] = []

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Top Navigation Bar
        nav_row = QHBoxLayout()
        self.back_btn = QPushButton("← Back to Dashboard")
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

        page_title = QLabel("Tickets, PNR Tracking & Train Telemetry")
        page_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #0b3c68;")
        nav_row.addWidget(page_title)

        nav_row.addStretch()

        self.refresh_btn = QPushButton("↻ Refresh Records")
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 6px 12px;
                color: #334155;
                font-weight: 600;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #e2e8f0; }
        """)
        self.refresh_btn.clicked.connect(self.fetch_bookings)
        nav_row.addWidget(self.refresh_btn)

        main_layout.addLayout(nav_row)

        # Main Tabs Container
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #cbd5e1;
                background-color: #ffffff;
                border-radius: 6px;
            }
            QTabBar::tab {
                background: #f1f5f9;
                color: #475569;
                font-weight: bold;
                padding: 8px 16px;
                margin-right: 4px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: #0b3c68;
                color: #ffffff;
            }
        """)

        # Tab 1: My Bookings
        self.bookings_tab = QWidget()
        self._setup_bookings_tab()
        self.tabs.addTab(self.bookings_tab, "📋 My Bookings History")

        # Tab 2: PNR Enquiry
        self.pnr_tab = QWidget()
        self._setup_pnr_tab()
        self.tabs.addTab(self.pnr_tab, "🔍 PNR Status Enquiry")

        # Tab 3: Live Train Status (HTTP)
        self.status_tab = QWidget()
        self._setup_status_tab()
        self.tabs.addTab(self.status_tab, "🚆 Live Train Status (REST)")

        main_layout.addWidget(self.tabs)

    # =========================================================================
    # Tab 1: Bookings Management
    # =========================================================================

    def _setup_bookings_tab(self) -> None:
        layout = QVBoxLayout(self.bookings_tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.bookings_status_label = QLabel("Click 'Refresh Records' to load reservations from the server.")
        self.bookings_status_label.setStyleSheet("color: #64748b; font-style: italic; font-size: 12px;")
        layout.addWidget(self.bookings_status_label)

        # Table starts empty
        self.bookings_table = QTableWidget(0, 8)
        self.bookings_table.setHorizontalHeaderLabels([
            "PNR", "Train", "Date", "Class", "Passengers", "Amount", "Status", "Actions"
        ])
        self.bookings_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.bookings_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.bookings_table.setAlternatingRowColors(True)
        self.bookings_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #e2e8f0;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #0b3c68;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
                padding: 6px;
                border: none;
            }
        """)
        layout.addWidget(self.bookings_table)

    def fetch_bookings(self) -> None:
        """Hydrates user bookings dynamically from backend TCP socket."""
        self.bookings_status_label.setText("Querying reservations from server...")
        try:
            resp = self.tcp_client.get_user_bookings()
            if resp.get("success"):
                bookings = resp.get("bookings", [])
                self._bookings_cache = bookings
                self._populate_bookings_table(bookings)
                self.bookings_status_label.setText(f"Loaded {len(bookings)} booking record(s).")
            else:
                self.bookings_table.setRowCount(0)
                msg = resp.get("message", "No bookings retrieved.")
                self.bookings_status_label.setText(f"✕ {msg}")
        except Exception as e:
            self.bookings_table.setRowCount(0)
            self.bookings_status_label.setText(f"✕ Network error: {str(e)}")
            QMessageBox.critical(self, "Network Failure", f"Failed to retrieve bookings: {str(e)}")

    def _populate_bookings_table(self, bookings: List[Dict[str, Any]]) -> None:
        """Populates the table with returned booking entries."""
        self.bookings_table.setRowCount(0)

        for row_idx, bk in enumerate(bookings):
            self.bookings_table.insertRow(row_idx)

            pnr = str(bk.get("pnr", "N/A"))
            train_desc = f"{bk.get('train_number', '')} {bk.get('train_name', '')}".strip()
            date = str(bk.get("date") or bk.get("journey_date") or "N/A")
            cls = str(bk.get("coach_class", bk.get("class", "N/A")))
            passengers_list = bk.get("passengers", [])
            p_count = str(len(passengers_list)) if passengers_list else str(bk.get("passenger_count", "1"))
            fare = f"₹ {float(bk.get('total_fare', bk.get('fare', 0.0))):.2f}"
            status = str(bk.get("status", "CONFIRMED")).upper()

            self.bookings_table.setItem(row_idx, 0, QTableWidgetItem(pnr))
            self.bookings_table.setItem(row_idx, 1, QTableWidgetItem(train_desc))
            self.bookings_table.setItem(row_idx, 2, QTableWidgetItem(date))
            self.bookings_table.setItem(row_idx, 3, QTableWidgetItem(cls))
            self.bookings_table.setItem(row_idx, 4, QTableWidgetItem(p_count))
            self.bookings_table.setItem(row_idx, 5, QTableWidgetItem(fare))

            # Status pill item
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            if status == "CANCELLED":
                status_item.setForeground(Qt.red)
            else:
                status_item.setForeground(Qt.darkGreen)
            self.bookings_table.setItem(row_idx, 6, status_item)

            # Actions Cell
            actions_widget = QWidget()
            act_layout = QHBoxLayout(actions_widget)
            act_layout.setContentsMargins(4, 2, 4, 2)
            act_layout.setSpacing(6)

            view_btn = QPushButton("View")
            view_btn.setCursor(Qt.PointingHandCursor)
            view_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0b3c68;
                    color: #ffffff;
                    border-radius: 3px;
                    padding: 3px 8px;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: #082947; }
            """)
            view_btn.clicked.connect(lambda ch, b=bk: self._show_ticket_modal(b))
            act_layout.addWidget(view_btn)

            cancel_btn = QPushButton("Cancel")
            cancel_btn.setCursor(Qt.PointingHandCursor)
            cancel_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ef4444;
                    color: #ffffff;
                    border-radius: 3px;
                    padding: 3px 8px;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: #dc2626; }
                QPushButton:disabled { background-color: #cbd5e1; }
            """)
            if status == "CANCELLED":
                cancel_btn.setEnabled(False)
            else:
                cancel_btn.clicked.connect(lambda ch, p=pnr: self._handle_cancellation(p))
            act_layout.addWidget(cancel_btn)

            self.bookings_table.setCellWidget(row_idx, 7, actions_widget)

    def _show_ticket_modal(self, booking: Dict[str, Any]) -> None:
        """Displays full digital e-ticket view in a clean modal dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Electronic Reservation Slip (ERS) - PNR {booking.get('pnr')}")
        dialog.setFixedWidth(480)
        dialog.setStyleSheet("background-color: #ffffff;")

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        # Ticket Header
        th = QFrame()
        th.setStyleSheet("background-color: #0b3c68; border-radius: 6px; padding: 12px;")
        th_layout = QVBoxLayout(th)
        t_logo = QLabel("🚆 INDIAN RAILWAYS PASSENGER RESERVATION")
        t_logo.setStyleSheet("color: #ffd8a8; font-weight: bold; font-size: 11px;")
        t_pnr = QLabel(f"PNR: {booking.get('pnr')}  |  Status: {booking.get('status', 'CONFIRMED')}")
        t_pnr.setStyleSheet("color: #ffffff; font-size: 15px; font-weight: bold;")
        th_layout.addWidget(t_logo)
        th_layout.addWidget(t_pnr)
        layout.addWidget(th)

        # Journey Details
        details_frame = QFrame()
        details_frame.setStyleSheet("border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px;")
        df_layout = QVBoxLayout(details_frame)

        train_name = f"{booking.get('train_number', '')} {booking.get('train_name', '')}".strip()
        route = f"{booking.get('source', '')} → {booking.get('destination', '')}"
        date = str(booking.get('date') or booking.get('journey_date') or 'N/A')
        cls = str(booking.get('coach_class', 'SL'))

        df_layout.addWidget(QLabel(f"<b>Train:</b> {train_name}"))
        df_layout.addWidget(QLabel(f"<b>Route:</b> {route}"))
        df_layout.addWidget(QLabel(f"<b>Date of Journey:</b> {date}  |  <b>Class:</b> {cls}"))
        layout.addWidget(details_frame)

        # Passengers list
        pass_label = QLabel("<b>Passenger Roster & Seat Allocations:</b>")
        layout.addWidget(pass_label)

        passengers = booking.get("passengers", [])
        if isinstance(passengers, list) and passengers:
            for p in passengers:
                p_text = f"• {p.get('name', 'Passenger')} ({p.get('age', '--')} yrs, {p.get('gender', '--')}) - Seat {p.get('seat_number', 'Allocated')}"
                layout.addWidget(QLabel(p_text))
        else:
            seats = booking.get("seats", [])
            seats_str = ", ".join(seats) if seats else "Confirmed"
            layout.addWidget(QLabel(f"• Allocated Seats: {seats_str}"))

        fare_lbl = QLabel(f"<b>Total Fare Paid:</b> ₹ {float(booking.get('total_fare', 0.0)):.2f}")
        fare_lbl.setStyleSheet("color: #d35400; font-size: 13px;")
        layout.addWidget(fare_lbl)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        close_btn.setStyleSheet("padding: 8px; background-color: #0b3c68; color: #ffffff; border-radius: 4px;")
        layout.addWidget(close_btn)

        dialog.exec()

    def _handle_cancellation(self, pnr: str) -> None:
        """Displays cancellation confirmation modal and executes cancellation via TCP."""
        confirm_text = (
            f"Are you sure you want to cancel ticket for PNR: {pnr}?\n\n"
            f"• Cancellation charges will be deducted as per IRCTC refund rules.\n"
            f"• Any allocated seats will be immediately released back into the server availability pool.\n"
            f"• This action cannot be reversed."
        )

        reply = QMessageBox.question(
            self,
            "Confirm Ticket Cancellation",
            confirm_text,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        try:
            resp = self.tcp_client.cancel_booking(pnr)
            if resp.get("success"):
                refund = resp.get("refund_amount", resp.get("refund", "Eligible Amount"))
                msg = f"✓ Ticket for PNR {pnr} cancelled successfully.\nRefund Advice: ₹ {refund}"
                QMessageBox.information(self, "Cancellation Confirmed", msg)
                self.fetch_bookings()
            else:
                err = resp.get("message", "Cancellation failed on server.")
                QMessageBox.critical(self, "Cancellation Error", err)
        except Exception as e:
            QMessageBox.critical(self, "Communication Error", f"Failed to cancel ticket: {str(e)}")

    # =========================================================================
    # Tab 2: PNR Enquiry
    # =========================================================================

    def _setup_pnr_tab(self) -> None:
        layout = QVBoxLayout(self.pnr_tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # PNR input bar
        input_card = QFrame()
        input_card.setStyleSheet("background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px;")
        ic_layout = QHBoxLayout(input_card)

        lbl = QLabel("Enter 10-Digit PNR Number:")
        lbl.setStyleSheet("font-weight: bold; color: #1e293b; font-size: 12px;")
        ic_layout.addWidget(lbl)

        self.pnr_enquiry_input = QLineEdit()
        self.pnr_enquiry_input.setPlaceholderText("e.g. 2451987340")
        self.pnr_enquiry_input.setMaxLength(10)
        self.pnr_enquiry_input.setStyleSheet("""
            QLineEdit {
                padding: 7px 10px;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
                letter-spacing: 1px;
            }
        """)
        ic_layout.addWidget(self.pnr_enquiry_input, 1)

        self.pnr_search_btn = QPushButton("🔍 Enquire Status")
        self.pnr_search_btn.setCursor(Qt.PointingHandCursor)
        self.pnr_search_btn.setStyleSheet("""
            QPushButton {
                background-color: #0b3c68;
                color: #ffffff;
                font-weight: bold;
                padding: 8px 18px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #082947; }
        """)
        self.pnr_search_btn.clicked.connect(self._handle_pnr_enquiry)
        ic_layout.addWidget(self.pnr_search_btn)

        layout.addWidget(input_card)

        # Dynamic PNR details card (starts blank)
        self.pnr_card = QFrame()
        self.pnr_card.setStyleSheet("background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 16px;")
        self.pnr_layout = QVBoxLayout(self.pnr_card)

        self.pnr_placeholder = QLabel("Enter a valid PNR number above to check reservation status.")
        self.pnr_placeholder.setStyleSheet("color: #64748b; font-style: italic; font-size: 13px; padding: 30px;")
        self.pnr_placeholder.setAlignment(Qt.AlignCenter)
        self.pnr_layout.addWidget(self.pnr_placeholder)

        layout.addWidget(self.pnr_card, 1)

    def _handle_pnr_enquiry(self) -> None:
        """Pre-flight validation and PNR status retrieval via TCP."""
        pnr = self.pnr_enquiry_input.text().strip()
        if not pnr:
            QMessageBox.warning(self, "Validation Error", "Please enter a PNR number.")
            return

        if len(pnr) != 10 or not pnr.isdigit():
            QMessageBox.warning(self, "Validation Error", "PNR must be an exact 10-digit numeric code.")
            return

        # Clear existing PNR card
        while self.pnr_layout.count():
            item = self.pnr_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.pnr_search_btn.setEnabled(False)
        self.pnr_search_btn.setText("Enquiring...")

        try:
            resp = self.tcp_client.pnr_enquiry(pnr)
            if resp.get("success"):
                bk = resp.get("booking", {})
                self._render_pnr_details(pnr, bk)
            else:
                msg = resp.get("message", f"PNR {pnr} not found in the reservation system.")
                lbl = QLabel(f"✕ {msg}")
                lbl.setStyleSheet("color: #ef4444; font-size: 13px; font-weight: bold; padding: 20px;")
                self.pnr_layout.addWidget(lbl)
        except Exception as e:
            lbl = QLabel(f"✕ Query failed: {str(e)}")
            lbl.setStyleSheet("color: #ef4444; font-size: 13px; padding: 20px;")
            self.pnr_layout.addWidget(lbl)
        finally:
            self.pnr_search_btn.setEnabled(True)
            self.pnr_search_btn.setText("🔍 Enquire Status")

    def _render_pnr_details(self, pnr: str, bk: Dict[str, Any]) -> None:
        """Renders structured PNR details from backend response."""
        train = bk.get("train_name", bk.get("train_number", "Express"))
        date = bk.get("journey_date", bk.get("date", "N/A"))
        status = str(bk.get("status", "CONFIRMED")).upper()
        chart_status = bk.get("chart_status", "CHART NOT PREPARED")

        header = QLabel(f"PNR: {pnr}  |  Train: {train}  |  Date: {date}")
        header.setStyleSheet("font-size: 15px; font-weight: bold; color: #0b3c68;")
        self.pnr_layout.addWidget(header)

        chart_lbl = QLabel(f"Charting Status: <b>{chart_status}</b>")
        chart_lbl.setStyleSheet("color: #d35400; font-size: 12px;")
        self.pnr_layout.addWidget(chart_lbl)

        overall_status_lbl = QLabel(f"Overall Booking Status: <b>{status}</b>")
        overall_status_lbl.setStyleSheet("color: #059669; font-size: 12px;")
        self.pnr_layout.addWidget(overall_status_lbl)

        # Passenger-wise status table
        passengers = bk.get("passengers", [])
        if passengers:
            table = QTableWidget(len(passengers), 4)
            table.setHorizontalHeaderLabels(["Passenger #", "Name", "Booking Status", "Current Status"])
            table.horizontalHeader().setStretchLastSection(True)
            for idx, p in enumerate(passengers):
                seat = str(p.get("seat_number", "CNF"))
                table.setItem(idx, 0, QTableWidgetItem(f"Passenger {idx + 1}"))
                table.setItem(idx, 1, QTableWidgetItem(p.get("name", "Passenger")))
                table.setItem(idx, 2, QTableWidgetItem(f"Seat {seat}"))
                table.setItem(idx, 3, QTableWidgetItem(status))
            self.pnr_layout.addWidget(table)

    # =========================================================================
    # Tab 3: Live Train Status (HTTP REST)
    # =========================================================================

    def _setup_status_tab(self) -> None:
        layout = QVBoxLayout(self.status_tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        query_card = QFrame()
        query_card.setStyleSheet("background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px;")
        qc_layout = QHBoxLayout(query_card)

        lbl = QLabel("Train Number:")
        lbl.setStyleSheet("font-weight: bold; color: #1e293b; font-size: 12px;")
        qc_layout.addWidget(lbl)

        self.train_status_input = QLineEdit()
        self.train_status_input.setPlaceholderText("e.g. 12301 / 12952")
        self.train_status_input.setStyleSheet("padding: 7px; border: 1px solid #cbd5e1; border-radius: 4px;")
        qc_layout.addWidget(self.train_status_input, 1)

        self.track_btn = QPushButton("📡 Query REST Running Status")
        self.track_btn.setCursor(Qt.PointingHandCursor)
        self.track_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-weight: bold;
                padding: 8px 18px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #0369a1; }
        """)
        self.track_btn.clicked.connect(self._handle_live_status)
        qc_layout.addWidget(self.track_btn)

        layout.addWidget(query_card)

        # Status Display Frame
        self.status_display_card = QFrame()
        self.status_display_card.setStyleSheet("background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 16px;")
        self.status_display_layout = QVBoxLayout(self.status_display_card)

        self.status_placeholder = QLabel("Enter a train number above to fetch live REST telemetry from the server.")
        self.status_placeholder.setStyleSheet("color: #64748b; font-style: italic; font-size: 13px; padding: 30px;")
        self.status_placeholder.setAlignment(Qt.AlignCenter)
        self.status_display_layout.addWidget(self.status_placeholder)

        layout.addWidget(self.status_display_card, 1)

    def _handle_live_status(self) -> None:
        """Fetches live train running position via HTTP REST endpoint."""
        train_num = self.train_status_input.text().strip()
        if not train_num:
            QMessageBox.warning(self, "Validation Error", "Please provide a train number.")
            return

        while self.status_display_layout.count():
            item = self.status_display_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.track_btn.setEnabled(False)
        self.track_btn.setText("Querying REST API...")

        try:
            resp = self.http_client.get_train_live_status(train_num)
            if resp.get("success"):
                t_name = resp.get("train_name", f"Train #{train_num}")
                current_station = resp.get("current_station", resp.get("last_station", "En Route"))
                delay_mins = resp.get("delay_minutes", resp.get("delay", 0))
                next_station = resp.get("next_station", "Approaching destination")

                title = QLabel(f"Live Telemetry: {t_name} ({train_num})")
                title.setStyleSheet("font-size: 15px; font-weight: bold; color: #0b3c68;")
                self.status_display_layout.addWidget(title)

                delay_text = "On Time" if delay_mins == 0 else f"Delayed by {delay_mins} minutes"
                delay_color = "#10b981" if delay_mins == 0 else "#ef4444"
                delay_lbl = QLabel(f"Running Status: <span style='color: {delay_color}; font-weight: bold;'>{delay_text}</span>")
                self.status_display_layout.addWidget(delay_lbl)

                pos_lbl = QLabel(f"<b>Current Location / Last Station Passed:</b> {current_station}")
                next_lbl = QLabel(f"<b>Next Scheduled Stoppage:</b> {next_station}")
                self.status_display_layout.addWidget(pos_lbl)
                self.status_display_layout.addWidget(next_lbl)
            else:
                msg = resp.get("message", f"Unable to fetch live status for train {train_num}.")
                lbl = QLabel(f"✕ {msg}")
                lbl.setStyleSheet("color: #ef4444; font-size: 13px; font-weight: bold; padding: 20px;")
                self.status_display_layout.addWidget(lbl)
        except Exception as e:
            lbl = QLabel(f"✕ REST call failed: {str(e)}")
            lbl.setStyleSheet("color: #ef4444; font-size: 13px; padding: 20px;")
            self.status_display_layout.addWidget(lbl)
        finally:
            self.track_btn.setEnabled(True)
            self.track_btn.setText("📡 Query REST Running Status")
