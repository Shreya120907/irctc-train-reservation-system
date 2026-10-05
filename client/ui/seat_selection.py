"""
Seat Selection View for IRCTC-Style Train Reservation Simulator
Interactive coach visualizer and real-time seat availability matrix.
Zero hardcoded data: the seat layout initializes completely empty and hydrates dynamically
from backend TCP availability responses.
"""

from typing import Any, Dict, List, Optional, Set
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
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


class SeatSelectionWidget(QWidget):
    """
    Dynamic seat allocation screen rendering coach layouts, berth types,
    and real-time booking occupancy.
    """

    proceed_to_booking = Signal(dict)
    back_requested = Signal()

    MAX_PASSENGERS = 6

    def __init__(self, tcp_client: TCPClient, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.tcp_client = tcp_client

        self.current_train_context: Dict[str, Any] = {}
        self.current_coach_class: str = "SL"
        self.base_fare: float = 0.0
        self.available_seats_data: List[Dict[str, Any]] = []
        self.selected_seats: Set[str] = set()

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # -------------------------------------------------------------
        # 1. Navigation & Train Information Header
        # -------------------------------------------------------------
        top_bar = QHBoxLayout()

        self.back_btn = QPushButton("← Back to Train List")
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
        top_bar.addWidget(self.back_btn)

        top_bar.addStretch()

        self.train_header_label = QLabel("Seat Selection - No Train Selected")
        self.train_header_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #0b3c68;")
        top_bar.addWidget(self.train_header_label)

        top_bar.addStretch()

        self.refresh_btn = QPushButton("↻ Refresh Seats")
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
        self.refresh_btn.clicked.connect(self.fetch_seat_availability)
        top_bar.addWidget(self.refresh_btn)

        main_layout.addLayout(top_bar)

        # -------------------------------------------------------------
        # 2. Class Selector Bar
        # -------------------------------------------------------------
        class_bar = QFrame()
        class_bar.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                padding: 8px 16px;
            }
        """)
        class_layout = QHBoxLayout(class_bar)
        class_layout.setSpacing(16)

        class_title = QLabel("Select Travel Class:")
        class_title.setStyleSheet("font-weight: bold; color: #1e293b; font-size: 12px;")
        class_layout.addWidget(class_title)

        self.class_button_group = QButtonGroup(self)
        self.class_buttons = {}

        for cls_code in ["SL", "3A", "2A", "1A", "CC", "2S"]:
            rbtn = QRadioButton(cls_code)
            rbtn.setStyleSheet("""
                QRadioButton {
                    font-size: 12px;
                    font-weight: bold;
                    color: #334155;
                }
                QRadioButton::indicator:checked {
                    background-color: #0b3c68;
                    border: 2px solid #0b3c68;
                }
            """)
            if cls_code == "SL":
                rbtn.setChecked(True)
            self.class_button_group.addButton(rbtn)
            self.class_buttons[cls_code] = rbtn
            rbtn.toggled.connect(lambda checked, c=cls_code: self._on_class_changed(c) if checked else None)
            class_layout.addWidget(rbtn)

        class_layout.addStretch()

        self.fare_pill = QLabel("Fare: ₹ 0 / seat")
        self.fare_pill.setStyleSheet("""
            background-color: #e0f2fe;
            color: #0369a1;
            font-weight: bold;
            font-size: 12px;
            padding: 4px 10px;
            border-radius: 4px;
        """)
        class_layout.addWidget(self.fare_pill)

        main_layout.addWidget(class_bar)

        # -------------------------------------------------------------
        # 3. Legend Bar
        # -------------------------------------------------------------
        legend_row = QHBoxLayout()
        legend_row.setAlignment(Qt.AlignCenter)
        legend_row.setSpacing(20)

        legend_row.addWidget(self._make_legend_item("#10b981", "Available"))
        legend_row.addWidget(self._make_legend_item("#ef4444", "Occupied / Booked"))
        legend_row.addWidget(self._make_legend_item("#f59e0b", "Selected (You)"))
        legend_row.addWidget(self._make_legend_item("#64748b", "Locked / Quota"))

        main_layout.addLayout(legend_row)

        # -------------------------------------------------------------
        # 4. Scrollable Seat Matrix Container (Hydrated Dynamically)
        # -------------------------------------------------------------
        self.matrix_scroll = QScrollArea()
        self.matrix_scroll.setWidgetResizable(True)
        self.matrix_scroll.setStyleSheet("QScrollArea { border: 1px solid #cbd5e1; background: #fafbfc; border-radius: 6px; }")

        self.seat_matrix_widget = QWidget()
        self.seat_matrix_layout = QVBoxLayout(self.seat_matrix_widget)
        self.seat_matrix_layout.setAlignment(Qt.AlignCenter)

        self.placeholder_label = QLabel("No seats loaded. Choose a class or refresh to query server.")
        self.placeholder_label.setStyleSheet("color: #64748b; font-size: 13px; font-style: italic; padding: 40px;")
        self.seat_matrix_layout.addWidget(self.placeholder_label)

        self.matrix_scroll.setWidget(self.seat_matrix_widget)
        main_layout.addWidget(self.matrix_scroll, 1)

        # -------------------------------------------------------------
        # 5. Bottom Checkout & Selection Summary Dock
        # -------------------------------------------------------------
        summary_dock = QFrame()
        summary_dock.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 12px 18px;
            }
        """)
        dock_layout = QHBoxLayout(summary_dock)

        summary_col = QVBoxLayout()
        self.selected_seats_label = QLabel("Selected Seats: None (Max 6 passengers)")
        self.selected_seats_label.setStyleSheet("font-weight: bold; color: #1e293b; font-size: 13px;")
        self.total_calc_label = QLabel("Total Estimated Fare: ₹ 0.00")
        self.total_calc_label.setStyleSheet("color: #d35400; font-size: 15px; font-weight: 800;")
        summary_col.addWidget(self.selected_seats_label)
        summary_col.addWidget(self.total_calc_label)
        dock_layout.addLayout(summary_col)

        dock_layout.addStretch()

        self.proceed_btn = QPushButton("Proceed to Passenger Details →")
        self.proceed_btn.setCursor(Qt.PointingHandCursor)
        self.proceed_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
                padding: 10px 20px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #059669; }
            QPushButton:disabled { background-color: #94a3b8; }
        """)
        self.proceed_btn.setEnabled(False)
        self.proceed_btn.clicked.connect(self._handle_proceed)
        dock_layout.addWidget(self.proceed_btn)

        main_layout.addWidget(summary_dock)

    def _make_legend_item(self, color: str, text: str) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        color_box = QLabel()
        color_box.setFixedSize(14, 14)
        color_box.setStyleSheet(f"background-color: {color}; border-radius: 3px;")
        layout.addWidget(color_box)

        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 11px; color: #475569; font-weight: 500;")
        layout.addWidget(lbl)
        return container

    def set_train_context(self, context: Dict[str, Any]) -> None:
        """Configures the current train and date parameters, then triggers seat fetch."""
        self.current_train_context = context
        train = context.get("train", {})
        train_no = train.get("train_number", train.get("number", "N/A"))
        train_name = train.get("train_name", train.get("name", "Express"))
        date = context.get("date", "")
        src = context.get("source", train.get("source", ""))
        dst = context.get("destination", train.get("destination", ""))

        self.train_header_label.setText(f"{train_no} - {train_name} | {src} → {dst} | {date}")

        # Clear previously selected seats
        self.selected_seats.clear()
        self._update_selection_summary()

        # Query backend for seat availability
        self.fetch_seat_availability()

    def _on_class_changed(self, new_class: str) -> None:
        self.current_coach_class = new_class
        self.selected_seats.clear()
        self._update_selection_summary()
        self.fetch_seat_availability()

    def fetch_seat_availability(self) -> None:
        """Fetches dynamic seat matrix via TCP socket."""
        if not self.current_train_context:
            return

        train = self.current_train_context.get("train", {})
        train_id = train.get("train_number") or train.get("id") or train.get("number")
        date_str = self.current_train_context.get("date")

        self.placeholder_label.setText("Querying live coach seat layout from server...")
        self.placeholder_label.setVisible(True)

        try:
            resp = self.tcp_client.get_seat_availability(
                train_id=train_id,
                coach_class=self.current_coach_class,
                date=date_str
            )

            if resp.get("success"):
                self.available_seats_data = resp.get("seats", [])
                self.base_fare = float(resp.get("fare", resp.get("base_fare", 450.0)))
                self.fare_pill.setText(f"Fare: ₹ {self.base_fare:.2f} / seat")
                self._render_seat_grid(self.available_seats_data)
            else:
                msg = resp.get("message", "Unable to retrieve seat availability.")
                self.placeholder_label.setText(f"✕ {msg}")
                self.placeholder_label.setVisible(True)
                QMessageBox.critical(self, "Seat Availability Error", msg)
        except Exception as e:
            self.placeholder_label.setText(f"✕ Network error: {str(e)}")
            self.placeholder_label.setVisible(True)
            QMessageBox.critical(self, "Network Failure", f"Failed to retrieve seats: {str(e)}")

    def _render_seat_grid(self, seats: List[Dict[str, Any]]) -> None:
        """Dynamically builds the coach seat grid UI from server payload."""
        # Clear existing layout
        while self.seat_matrix_layout.count():
            item = self.seat_matrix_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # Clean nested layout items
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()

        if not seats:
            self.placeholder_label = QLabel(
                f"No seat records returned for Class {self.current_coach_class} on this date."
            )
            self.placeholder_label.setStyleSheet("color: #64748b; font-size: 13px; font-style: italic; padding: 40px;")
            self.seat_matrix_layout.addWidget(self.placeholder_label)
            return

        coach_frame = QFrame()
        coach_frame.setStyleSheet("""
            QFrame {
                background-color: #f1f5f9;
                border: 2px solid #cbd5e1;
                border-radius: 8px;
                padding: 16px;
            }
        """)
        grid = QGridLayout(coach_frame)
        grid.setSpacing(8)

        # Standard layout: 6 columns (Columns 0, 1, 2 = Left Bay; Column 3 = Gangway Aisle; Columns 4, 5 = Side Bay)
        cols_per_row = 6
        for idx, seat in enumerate(seats):
            seat_num = str(seat.get("seat_number", idx + 1))
            berth_type = str(seat.get("berth", seat.get("type", "B")))
            status = str(seat.get("status", "AVAILABLE")).upper()

            btn = QPushButton(f"{seat_num}\n{berth_type}")
            btn.setFixedSize(54, 48)

            row = idx // cols_per_row
            col_in_bay = idx % cols_per_row

            # Shift columns for the central aisle
            col = col_in_bay if col_in_bay < 3 else col_in_bay + 1

            if status in ("AVAILABLE", "VACANT"):
                if seat_num in self.selected_seats:
                    btn.setStyleSheet(self._seat_btn_style("#f59e0b", "#ffffff", True))
                else:
                    btn.setStyleSheet(self._seat_btn_style("#10b981", "#ffffff", False))
                btn.setCursor(Qt.PointingHandCursor)
                btn.clicked.connect(lambda ch, s=seat_num, b=btn: self._toggle_seat_selection(s, b))
            else:
                # Booked or reserved
                btn.setStyleSheet(self._seat_btn_style("#ef4444", "#ffffff", False))
                btn.setEnabled(False)
                btn.setToolTip(f"Seat {seat_num} ({berth_type}) - Booked")

            grid.addWidget(btn, row, col)

        self.seat_matrix_layout.addWidget(coach_frame)
        self._update_selection_summary()

    def _seat_btn_style(self, bg: str, text: str, selected: bool) -> str:
        border = "2px solid #d97706" if selected else "1px solid rgba(0,0,0,0.1)"
        return f"""
            QPushButton {{
                background-color: {bg};
                color: {text};
                border: {border};
                border-radius: 6px;
                font-weight: bold;
                font-size: 10px;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
        """

    def _toggle_seat_selection(self, seat_num: str, btn: QPushButton) -> None:
        """Toggles user selection for a clicked seat."""
        if seat_num in self.selected_seats:
            self.selected_seats.remove(seat_num)
            btn.setStyleSheet(self._seat_btn_style("#10b981", "#ffffff", False))
        else:
            if len(self.selected_seats) >= self.MAX_PASSENGERS:
                QMessageBox.warning(
                    self,
                    "Selection Limit",
                    f"You may book a maximum of {self.MAX_PASSENGERS} passengers per ticket."
                )
                return
            self.selected_seats.add(seat_num)
            btn.setStyleSheet(self._seat_btn_style("#f59e0b", "#ffffff", True))

        self._update_selection_summary()

    def _update_selection_summary(self) -> None:
        """Recalculates dynamic fare and updates checkout action state."""
        count = len(self.selected_seats)
        if count == 0:
            self.selected_seats_label.setText("Selected Seats: None (Max 6 passengers)")
            self.total_calc_label.setText(f"Total Estimated Fare: ₹ 0.00")
            self.proceed_btn.setEnabled(False)
        else:
            seats_str = ", ".join(sorted(self.selected_seats, key=lambda x: int(x) if x.isdigit() else x))
            self.selected_seats_label.setText(f"Selected Seats ({count}): {seats_str}")
            total = count * self.base_fare
            self.total_calc_label.setText(f"Total Estimated Fare: ₹ {total:.2f}")
            self.proceed_btn.setEnabled(True)

    def _handle_proceed(self) -> None:
        """Validates seat selection and forwards data to Passenger Details screen."""
        if not self.selected_seats:
            QMessageBox.warning(self, "Selection Required", "Please select at least one seat to proceed.")
            return

        booking_draft = {
            "train_context": self.current_train_context,
            "coach_class": self.current_coach_class,
            "base_fare": self.base_fare,
            "selected_seats": sorted(list(self.selected_seats), key=lambda x: int(x) if x.isdigit() else x),
            "total_fare": len(self.selected_seats) * self.base_fare
        }
        self.proceed_to_booking.emit(booking_draft)
