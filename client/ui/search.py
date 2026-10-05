"""
Train Search View for IRCTC-Style Train Reservation Simulator
Handles station queries, date constraints, quota filtering, and dynamic train results hydration.
Zero hardcoded data: the train table initializes empty and hydrates only from backend TCP responses.
"""

from typing import Any, Dict, List, Optional
from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
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


class SearchWidget(QWidget):
    """
    Search interface with pre-flight origin-destination validation, date enforcement,
    and dynamically hydrated train schedules.
    """

    train_selected = Signal(dict)   # Emits selected train object + search parameters
    back_requested = Signal()

    def __init__(self, tcp_client: TCPClient, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.tcp_client = tcp_client
        self._search_results: List[Dict[str, Any]] = []

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Header navigation row
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

        page_title = QLabel("🚆 Book Your Train Journey")
        page_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #0b3c68;")
        nav_row.addWidget(page_title)
        nav_row.addStretch()

        main_layout.addLayout(nav_row)

        # Search Query Filter Card
        filter_card = QFrame()
        filter_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 16px;
            }
        """)
        filter_layout = QVBoxLayout(filter_card)
        filter_layout.setSpacing(12)

        # Station selection row
        station_row = QHBoxLayout()
        station_row.setSpacing(10)

        # Origin
        src_col = QVBoxLayout()
        src_label = QLabel("From Station *")
        src_label.setStyleSheet("font-size: 11px; font-weight: 600; color: #1e293b;")
        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("Origin Station (e.g. NDLS / New Delhi)")
        self._style_input(self.source_input)
        src_col.addWidget(src_label)
        src_col.addWidget(self.source_input)
        station_row.addLayout(src_col, 2)

        # Swap button
        swap_col = QVBoxLayout()
        swap_col.setAlignment(Qt.AlignBottom)
        self.swap_btn = QPushButton("⇄")
        self.swap_btn.setToolTip("Swap origin and destination stations")
        self.swap_btn.setCursor(Qt.PointingHandCursor)
        self.swap_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                font-size: 16px;
                font-weight: bold;
                padding: 6px 10px;
                margin-bottom: 2px;
            }
            QPushButton:hover { background-color: #e2e8f0; }
        """)
        self.swap_btn.clicked.connect(self._swap_stations)
        swap_col.addWidget(self.swap_btn)
        station_row.addLayout(swap_col)

        # Destination
        dst_col = QVBoxLayout()
        dst_label = QLabel("To Station *")
        dst_label.setStyleSheet("font-size: 11px; font-weight: 600; color: #1e293b;")
        self.dest_input = QLineEdit()
        self.dest_input.setPlaceholderText("Destination Station (e.g. BCT / Mumbai)")
        self._style_input(self.dest_input)
        dst_col.addWidget(dst_label)
        dst_col.addWidget(self.dest_input)
        station_row.addLayout(dst_col, 2)

        # Journey Date
        date_col = QVBoxLayout()
        date_label = QLabel("Journey Date *")
        date_label.setStyleSheet("font-size: 11px; font-weight: 600; color: #1e293b;")
        self.date_input = QDateEdit()
        self.date_input.setCalendarPopup(True)
        self.date_input.setDate(QDate.currentDate())
        self.date_input.setMinimumDate(QDate.currentDate())
        self.date_input.setDisplayFormat("yyyy-MM-dd")
        self.date_input.setStyleSheet("""
            QDateEdit {
                padding: 6px;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                font-size: 12px;
            }
        """)
        date_col.addWidget(date_label)
        date_col.addWidget(self.date_input)
        station_row.addLayout(date_col, 1)

        filter_layout.addLayout(station_row)

        # Preferences row: Quota, Class, Submit
        pref_row = QHBoxLayout()
        pref_row.setSpacing(12)

        # Quota
        quota_col = QVBoxLayout()
        quota_label = QLabel("Booking Quota")
        quota_label.setStyleSheet("font-size: 11px; font-weight: 600; color: #1e293b;")
        self.quota_combo = QComboBox()
        self.quota_combo.addItems([
            "GENERAL (GN)",
            "TATKAL (TQ)",
            "LADIES (LD)",
            "LOWER BERTH / SR. CITIZEN (SS)"
        ])
        self.quota_combo.setStyleSheet("padding: 6px; border: 1px solid #cbd5e1; border-radius: 4px;")
        quota_col.addWidget(quota_label)
        quota_col.addWidget(self.quota_combo)
        pref_row.addLayout(quota_col, 1)

        # Class Filter
        class_col = QVBoxLayout()
        class_label = QLabel("Coach Class")
        class_label.setStyleSheet("font-size: 11px; font-weight: 600; color: #1e293b;")
        self.class_combo = QComboBox()
        self.class_combo.addItems([
            "All Classes",
            "1A (AC First Class)",
            "2A (AC 2 Tier)",
            "3A (AC 3 Tier)",
            "SL (Sleeper)",
            "CC (AC Chair Car)",
            "2S (Second Sitting)"
        ])
        self.class_combo.setStyleSheet("padding: 6px; border: 1px solid #cbd5e1; border-radius: 4px;")
        class_col.addWidget(class_label)
        class_col.addWidget(self.class_combo)
        pref_row.addLayout(class_col, 1)

        # Search Button
        search_col = QVBoxLayout()
        search_col.setAlignment(Qt.AlignBottom)
        self.search_btn = QPushButton("🔍 Search Trains")
        self.search_btn.setCursor(Qt.PointingHandCursor)
        self.search_btn.setStyleSheet("""
            QPushButton {
                background-color: #d35400;
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 24px;
                border-radius: 6px;
                margin-bottom: 2px;
            }
            QPushButton:hover { background-color: #b94400; }
            QPushButton:pressed { background-color: #9c3600; }
        """)
        self.search_btn.clicked.connect(self._handle_search)
        search_col.addWidget(self.search_btn)
        pref_row.addLayout(search_col)

        filter_layout.addLayout(pref_row)
        main_layout.addWidget(filter_card)

        # Results Overview Bar
        self.status_bar = QLabel("Search for trains between origin and destination to view schedules.")
        self.status_bar.setStyleSheet("font-size: 12px; color: #64748b; font-style: italic;")
        main_layout.addWidget(self.status_bar)

        # Results Table (Starts empty - zero hardcoded data)
        self.results_table = QTableWidget(0, 8)
        self.results_table.setHorizontalHeaderLabels([
            "Train No.", "Train Name", "Origin → Destination",
            "Departure", "Arrival", "Duration", "Available Classes", "Action"
        ])
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #0b3c68;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
                padding: 8px;
                border: none;
            }
        """)
        main_layout.addWidget(self.results_table)

    def _style_input(self, widget: QLineEdit) -> None:
        widget.setStyleSheet("""
            QLineEdit {
                padding: 7px 10px;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                font-size: 12px;
            }
            QLineEdit:focus { border: 1px solid #0b3c68; }
        """)

    def _swap_stations(self) -> None:
        """Swaps source and destination text fields."""
        src = self.source_input.text()
        self.source_input.setText(self.dest_input.text())
        self.dest_input.setText(src)

    def _handle_search(self) -> None:
        """Pre-flight input validation followed by TCP train search query."""
        source = self.source_input.text().strip()
        dest = self.dest_input.text().strip()
        date_str = self.date_input.date().toString("yyyy-MM-dd")
        quota = self.quota_combo.currentText().split()[0]

        class_text = self.class_combo.currentText()
        coach_class = None if class_text == "All Classes" else class_text.split()[0]

        # Pre-flight checks
        if not source:
            QMessageBox.warning(self, "Validation Error", "Please provide an origin / departure station.")
            self.source_input.setFocus()
            return

        if not dest:
            QMessageBox.warning(self, "Validation Error", "Please provide a destination / arrival station.")
            self.dest_input.setFocus()
            return

        if source.upper() == dest.upper():
            QMessageBox.warning(
                self,
                "Validation Error",
                "Origin and destination stations cannot be identical."
            )
            self.dest_input.setFocus()
            return

        if self.date_input.date() < QDate.currentDate():
            QMessageBox.warning(
                self,
                "Validation Error",
                "Journey date cannot be in the past."
            )
            return

        self.search_btn.setEnabled(False)
        self.search_btn.setText("Searching...")
        self.status_bar.setText(f"Searching trains between {source.upper()} and {dest.upper()} on {date_str}...")
        self.results_table.setRowCount(0)

        try:
            resp = self.tcp_client.search_trains(
                source=source,
                destination=dest,
                date=date_str,
                quota=quota,
                coach_class=coach_class
            )

            if resp.get("success"):
                trains = resp.get("trains", [])
                self._search_results = trains
                if not trains:
                    self.status_bar.setText(
                        f"No trains found operating between {source.upper()} and {dest.upper()} on {date_str}."
                    )
                else:
                    self.status_bar.setText(f"Found {len(trains)} train(s) matching your criteria.")
                    self._populate_results(trains, date_str, quota)
            else:
                err_msg = resp.get("message", "Failed to retrieve train schedules from server.")
                self.status_bar.setText(f"✕ {err_msg}")
                QMessageBox.critical(self, "Search Error", err_msg)
        except Exception as e:
            self.status_bar.setText(f"✕ Network error: {str(e)}")
            QMessageBox.critical(self, "Network Failure", f"Could not connect to train search service: {str(e)}")
        finally:
            self.search_btn.setEnabled(True)
            self.search_btn.setText("🔍 Search Trains")

    def _populate_results(self, trains: List[Dict[str, Any]], date_str: str, quota: str) -> None:
        """Populates the train search table dynamically from server response."""
        self.results_table.setRowCount(0)
        for row_idx, train in enumerate(trains):
            self.results_table.insertRow(row_idx)

            train_no = str(train.get("train_number", train.get("number", "N/A")))
            train_name = str(train.get("train_name", train.get("name", "Express")))
            route = f"{train.get('source', '')} → {train.get('destination', '')}"
            dep = str(train.get("departure_time", train.get("departure", "--:--")))
            arr = str(train.get("arrival_time", train.get("arrival", "--:--")))
            duration = str(train.get("duration", "--"))

            # Classes info
            classes_info = train.get("available_classes", train.get("classes", []))
            if isinstance(classes_info, list):
                class_str = ", ".join(str(c) for c in classes_info)
            elif isinstance(classes_info, dict):
                class_str = ", ".join(f"{k} ({v})" for k, v in classes_info.items())
            else:
                class_str = str(classes_info) or "1A, 2A, 3A, SL"

            self.results_table.setItem(row_idx, 0, QTableWidgetItem(train_no))
            self.results_table.setItem(row_idx, 1, QTableWidgetItem(train_name))
            self.results_table.setItem(row_idx, 2, QTableWidgetItem(route))
            self.results_table.setItem(row_idx, 3, QTableWidgetItem(dep))
            self.results_table.setItem(row_idx, 4, QTableWidgetItem(arr))
            self.results_table.setItem(row_idx, 5, QTableWidgetItem(duration))
            self.results_table.setItem(row_idx, 6, QTableWidgetItem(class_str))

            # Select / Book Button
            book_btn = QPushButton("Select Seats →")
            book_btn.setCursor(Qt.PointingHandCursor)
            book_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0b3c68;
                    color: #ffffff;
                    font-weight: bold;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: #082947; }
            """)
            # Connect with closure capturing current train
            book_btn.clicked.connect(lambda checked, t=train: self._select_train(t, date_str, quota))
            self.results_table.setCellWidget(row_idx, 7, book_btn)

    def _select_train(self, train: Dict[str, Any], date_str: str, quota: str) -> None:
        """Emits selection with full train dictionary and context parameters."""
        selection_data = {
            "train": train,
            "date": date_str,
            "quota": quota,
            "source": self.source_input.text().strip().upper(),
            "destination": self.dest_input.text().strip().upper()
        }
        self.train_selected.emit(selection_data)
