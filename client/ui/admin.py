"""
Admin Operations View for IRCTC-Style Train Reservation Simulator
Provides train scheduling, cancellation workflows, passenger manifests,
REST health telemetry, and emergency UDP broadcast dispatches.
Zero direct DB access: all admin actions route strictly via network clients.
"""

from typing import Any, Dict, List, Optional
from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
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


class AdminWidget(QWidget):
    """
    Railway Operations & Administration interface for fleet management,
    telemetry, and live network broadcasts.
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

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Top Navigation
        nav_row = QHBoxLayout()
        self.back_btn = QPushButton("← Return to Dashboard")
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

        page_title = QLabel("⚙ IRCTC Operations & System Administration")
        page_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #d35400;")
        nav_row.addWidget(page_title)

        nav_row.addStretch()

        self.refresh_btn = QPushButton("↻ Refresh Telemetry")
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
        self.refresh_btn.clicked.connect(self.refresh_all_admin_data)
        nav_row.addWidget(self.refresh_btn)

        main_layout.addLayout(nav_row)

        # Tabs Container
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
                background: #d35400;
                color: #ffffff;
            }
        """)

        # Tab 1: Train Fleet Management
        self.fleet_tab = QWidget()
        self._setup_fleet_tab()
        self.tabs.addTab(self.fleet_tab, "🚆 Train Fleet Management")

        # Tab 2: Passenger Manifest
        self.manifest_tab = QWidget()
        self._setup_manifest_tab()
        self.tabs.addTab(self.manifest_tab, "📋 Passenger Manifest")

        # Tab 3: System Health & Telemetry (REST)
        self.telemetry_tab = QWidget()
        self._setup_telemetry_tab()
        self.tabs.addTab(self.telemetry_tab, "📊 System Health & Metrics")

        # Tab 4: Live Announcements (Broadcasts)
        self.broadcast_tab = QWidget()
        self._setup_broadcast_tab()
        self.tabs.addTab(self.broadcast_tab, "📢 Emergency Broadcasts")

        main_layout.addWidget(self.tabs)

    # =========================================================================
    # Tab 1: Fleet Management
    # =========================================================================

    def _setup_fleet_tab(self) -> None:
        layout = QVBoxLayout(self.fleet_tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        top_actions = QHBoxLayout()
        self.fleet_status_label = QLabel("Click 'Load Trains' to fetch registry from server.")
        self.fleet_status_label.setStyleSheet("color: #64748b; font-style: italic; font-size: 12px;")
        top_actions.addWidget(self.fleet_status_label)
        top_actions.addStretch()

        self.add_train_btn = QPushButton("+ Register New Train Schedule")
        self.add_train_btn.setCursor(Qt.PointingHandCursor)
        self.add_train_btn.setStyleSheet("""
            QPushButton {
                background-color: #0b3c68;
                color: #ffffff;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #082947; }
        """)
        self.add_train_btn.clicked.connect(self._open_add_train_dialog)
        top_actions.addWidget(self.add_train_btn)

        self.load_trains_btn = QPushButton("Load Trains")
        self.load_trains_btn.setCursor(Qt.PointingHandCursor)
        self.load_trains_btn.setStyleSheet("""
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
        self.load_trains_btn.clicked.connect(self.fetch_fleet)
        top_actions.addWidget(self.load_trains_btn)

        layout.addLayout(top_actions)

        # Table starts empty
        self.fleet_table = QTableWidget(0, 8)
        self.fleet_table.setHorizontalHeaderLabels([
            "Train No.", "Train Name", "Route", "Dep", "Arr", "Classes", "Status", "Actions"
        ])
        self.fleet_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.fleet_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.fleet_table.setAlternatingRowColors(True)
        self.fleet_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #e2e8f0;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #1e293b;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
                padding: 6px;
                border: none;
            }
        """)
        layout.addWidget(self.fleet_table)

    def fetch_fleet(self) -> None:
        """Hydrates train catalog dynamically from TCP server."""
        self.fleet_status_label.setText("Querying train fleet from server...")
        try:
            resp = self.tcp_client.admin_get_trains()
            if resp.get("success"):
                trains = resp.get("trains", [])
                self._populate_fleet_table(trains)
                self.fleet_status_label.setText(f"Loaded {len(trains)} registered train(s).")
            else:
                self.fleet_table.setRowCount(0)
                msg = resp.get("message", "No trains returned by server.")
                self.fleet_status_label.setText(f"✕ {msg}")
        except Exception as e:
            self.fleet_table.setRowCount(0)
            self.fleet_status_label.setText(f"✕ Network error: {str(e)}")
            QMessageBox.critical(self, "Fleet Query Failure", f"Failed to fetch train fleet: {str(e)}")

    def _populate_fleet_table(self, trains: List[Dict[str, Any]]) -> None:
        self.fleet_table.setRowCount(0)
        for row_idx, t in enumerate(trains):
            self.fleet_table.insertRow(row_idx)

            t_no = str(t.get("train_number", t.get("number", "N/A")))
            t_name = str(t.get("train_name", t.get("name", "Express")))
            route = f"{t.get('source', '')} → {t.get('destination', '')}"
            dep = str(t.get("departure_time", "--:--"))
            arr = str(t.get("arrival_time", "--:--"))
            classes = ", ".join(t.get("classes", ["1A", "2A", "3A", "SL"])) if isinstance(t.get("classes"), list) else str(t.get("classes", "All"))
            status = str(t.get("status", "ACTIVE")).upper()

            self.fleet_table.setItem(row_idx, 0, QTableWidgetItem(t_no))
            self.fleet_table.setItem(row_idx, 1, QTableWidgetItem(t_name))
            self.fleet_table.setItem(row_idx, 2, QTableWidgetItem(route))
            self.fleet_table.setItem(row_idx, 3, QTableWidgetItem(dep))
            self.fleet_table.setItem(row_idx, 4, QTableWidgetItem(arr))
            self.fleet_table.setItem(row_idx, 5, QTableWidgetItem(classes))

            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            if status == "CANCELLED":
                status_item.setForeground(Qt.red)
            else:
                status_item.setForeground(Qt.darkGreen)
            self.fleet_table.setItem(row_idx, 6, status_item)

            # Action button
            cancel_btn = QPushButton("Cancel Run")
            cancel_btn.setCursor(Qt.PointingHandCursor)
            cancel_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ef4444;
                    color: #ffffff;
                    border-radius: 3px;
                    padding: 3px 6px;
                    font-size: 10px;
                }
                QPushButton:hover { background-color: #dc2626; }
                QPushButton:disabled { background-color: #cbd5e1; }
            """)
            if status == "CANCELLED":
                cancel_btn.setEnabled(False)
            else:
                cancel_btn.clicked.connect(lambda ch, tid=t_no: self._handle_cancel_train(tid))
            self.fleet_table.setCellWidget(row_idx, 7, cancel_btn)

    def _open_add_train_dialog(self) -> None:
        """Modal dialog to configure and submit a new train schedule."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Register New Train Schedule")
        dialog.setFixedWidth(440)
        dialog.setStyleSheet("background-color: #ffffff;")

        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)

        title = QLabel("New Train Registration")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #0b3c68;")
        layout.addWidget(title)

        # Fields
        t_no = QLineEdit()
        t_no.setPlaceholderText("Train Number (e.g. 12951)")
        t_name = QLineEdit()
        t_name.setPlaceholderText("Train Name (e.g. Mumbai Rajdhani)")
        src = QLineEdit()
        src.setPlaceholderText("Origin Station (e.g. BCT)")
        dst = QLineEdit()
        dst.setPlaceholderText("Destination Station (e.g. NDLS)")
        dep = QLineEdit()
        dep.setPlaceholderText("Departure Time (HH:MM e.g. 16:30)")
        arr = QLineEdit()
        arr.setPlaceholderText("Arrival Time (HH:MM e.g. 08:30)")

        for f in [t_no, t_name, src, dst, dep, arr]:
            f.setStyleSheet("padding: 6px; border: 1px solid #cbd5e1; border-radius: 4px;")
            layout.addWidget(f)

        submit_btn = QPushButton("Save Train Schedule")
        submit_btn.setStyleSheet("padding: 8px; background-color: #0b3c68; color: #ffffff; font-weight: bold; border-radius: 4px;")

        def on_submit():
            # Pre-flight validation
            if not t_no.text().strip() or not t_name.text().strip():
                QMessageBox.warning(dialog, "Validation Error", "Train number and name are required.")
                return
            if not src.text().strip() or not dst.text().strip():
                QMessageBox.warning(dialog, "Validation Error", "Origin and destination stations are required.")
                return

            train_payload = {
                "train_number": t_no.text().strip(),
                "train_name": t_name.text().strip(),
                "source": src.text().strip().upper(),
                "destination": dst.text().strip().upper(),
                "departure_time": dep.text().strip() or "00:00",
                "arrival_time": arr.text().strip() or "00:00",
                "classes": ["1A", "2A", "3A", "SL"]
            }

            try:
                resp = self.tcp_client.admin_add_train(train_payload)
                if resp.get("success"):
                    QMessageBox.information(dialog, "Success", f"Train {t_no.text()} registered successfully.")
                    dialog.accept()
                    self.fetch_fleet()
                else:
                    QMessageBox.critical(dialog, "Error", resp.get("message", "Failed to add train."))
            except Exception as e:
                QMessageBox.critical(dialog, "Network Error", str(e))

        submit_btn.clicked.connect(on_submit)
        layout.addWidget(submit_btn)
        dialog.exec()

    def _handle_cancel_train(self, train_id: str) -> None:
        """Confirmation dialog before deactivating a train run."""
        reply = QMessageBox.question(
            self,
            "Confirm Train Cancellation",
            f"Are you sure you want to cancel train {train_id}?\nAll passenger reservations will be flagged for refund.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                resp = self.tcp_client.admin_cancel_train(train_id, "Operational exigency")
                if resp.get("success"):
                    QMessageBox.information(self, "Success", f"Train {train_id} cancelled.")
                    self.fetch_fleet()
                else:
                    QMessageBox.critical(self, "Error", resp.get("message", "Cancellation failed."))
            except Exception as e:
                QMessageBox.critical(self, "Network Error", str(e))

    # =========================================================================
    # Tab 2: Passenger Manifest
    # =========================================================================

    def _setup_manifest_tab(self) -> None:
        layout = QVBoxLayout(self.manifest_tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        query_row = QHBoxLayout()
        query_row.addWidget(QLabel("Train No:"))
        self.manifest_train_input = QLineEdit()
        self.manifest_train_input.setPlaceholderText("e.g. 12301")
        self.manifest_train_input.setStyleSheet("padding: 6px; border: 1px solid #cbd5e1; border-radius: 4px;")
        query_row.addWidget(self.manifest_train_input)

        query_row.addWidget(QLabel("Date:"))
        self.manifest_date_input = QDateEdit()
        self.manifest_date_input.setCalendarPopup(True)
        self.manifest_date_input.setDate(QDate.currentDate())
        self.manifest_date_input.setDisplayFormat("yyyy-MM-dd")
        self.manifest_date_input.setStyleSheet("padding: 6px; border: 1px solid #cbd5e1; border-radius: 4px;")
        query_row.addWidget(self.manifest_date_input)

        self.fetch_manifest_btn = QPushButton("Generate Passenger Manifest")
        self.fetch_manifest_btn.setCursor(Qt.PointingHandCursor)
        self.fetch_manifest_btn.setStyleSheet("""
            QPushButton {
                background-color: #0b3c68;
                color: #ffffff;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #082947; }
        """)
        self.fetch_manifest_btn.clicked.connect(self._handle_fetch_manifest)
        query_row.addWidget(self.fetch_manifest_btn)
        layout.addLayout(query_row)

        self.manifest_status_label = QLabel("Specify train number and date to inspect official manifest.")
        self.manifest_status_label.setStyleSheet("color: #64748b; font-style: italic; font-size: 12px;")
        layout.addWidget(self.manifest_status_label)

        self.manifest_table = QTableWidget(0, 6)
        self.manifest_table.setHorizontalHeaderLabels([
            "PNR", "Passenger Name", "Age / Gender", "Coach / Class", "Seat", "Status"
        ])
        self.manifest_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.manifest_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.manifest_table.setAlternatingRowColors(True)
        layout.addWidget(self.manifest_table)

    def _handle_fetch_manifest(self) -> None:
        """Fetches passenger manifest dynamically via TCP."""
        train_no = self.manifest_train_input.text().strip()
        date_str = self.manifest_date_input.date().toString("yyyy-MM-dd")

        if not train_no:
            QMessageBox.warning(self, "Validation Error", "Please provide a valid train number.")
            return

        self.manifest_status_label.setText(f"Querying manifest for Train {train_no} on {date_str}...")
        self.manifest_table.setRowCount(0)

        try:
            resp = self.tcp_client.admin_get_manifest(train_no, date_str)
            if resp.get("success"):
                manifest = resp.get("manifest", resp.get("passengers", []))
                self.manifest_table.setRowCount(len(manifest))
                for idx, p in enumerate(manifest):
                    self.manifest_table.setItem(idx, 0, QTableWidgetItem(str(p.get("pnr", "N/A"))))
                    self.manifest_table.setItem(idx, 1, QTableWidgetItem(str(p.get("name", "Passenger"))))
                    self.manifest_table.setItem(idx, 2, QTableWidgetItem(f"{p.get('age', '--')} / {p.get('gender', '--')}"))
                    self.manifest_table.setItem(idx, 3, QTableWidgetItem(str(p.get("coach_class", p.get("coach", "SL")))))
                    self.manifest_table.setItem(idx, 4, QTableWidgetItem(str(p.get("seat_number", p.get("seat", "--")))))
                    self.manifest_table.setItem(idx, 5, QTableWidgetItem(str(p.get("status", "CNF"))))

                self.manifest_status_label.setText(f"Loaded {len(manifest)} passenger record(s).")
            else:
                msg = resp.get("message", "No manifest data available for the given train.")
                self.manifest_status_label.setText(f"✕ {msg}")
        except Exception as e:
            self.manifest_status_label.setText(f"✕ Query failed: {str(e)}")
            QMessageBox.critical(self, "Manifest Failure", str(e))

    # =========================================================================
    # Tab 3: System Health & Telemetry (HTTP REST)
    # =========================================================================

    def _setup_telemetry_tab(self) -> None:
        layout = QVBoxLayout(self.telemetry_tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        top_row = QHBoxLayout()
        title = QLabel("Real-Time Server Health & Network Telemetry (HTTP REST)")
        title.setStyleSheet("font-size: 13px; font-weight: bold; color: #0b3c68;")
        top_row.addWidget(title)
        top_row.addStretch()

        self.btn_poll_metrics = QPushButton("Query REST Metrics")
        self.btn_poll_metrics.setCursor(Qt.PointingHandCursor)
        self.btn_poll_metrics.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #0369a1; }
        """)
        self.btn_poll_metrics.clicked.connect(self._poll_telemetry)
        top_row.addWidget(self.btn_poll_metrics)
        layout.addLayout(top_row)

        # Telemetry Card
        self.metrics_card = QFrame()
        self.metrics_card.setStyleSheet("background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; padding: 16px;")
        self.metrics_layout = QVBoxLayout(self.metrics_card)

        self.lbl_t_health = QLabel("REST Gateway Status: Unknown")
        self.lbl_t_conns = QLabel("Active Socket Connections: --")
        self.lbl_t_uptime = QLabel("Server Process Uptime: --")
        self.lbl_t_db = QLabel("Database Connectivity State: --")

        for lbl in [self.lbl_t_health, self.lbl_t_conns, self.lbl_t_uptime, self.lbl_t_db]:
            lbl.setStyleSheet("font-size: 12px; color: #1e293b; padding: 4px;")
            self.metrics_layout.addWidget(lbl)

        layout.addWidget(self.metrics_card)
        layout.addStretch()

    def _poll_telemetry(self) -> None:
        """Queries health and metrics via HTTP client."""
        health = self.http_client.check_health()
        metrics = self.http_client.get_system_metrics()

        if health.get("success"):
            self.lbl_t_health.setText(f"REST Gateway Status: <b>Online ({health.get('status', 'OK')})</b>")
            self.lbl_t_health.setStyleSheet("color: #047857; font-size: 12px; padding: 4px;")
        else:
            self.lbl_t_health.setText(f"REST Gateway Status: <b>Offline ({health.get('message', 'Unreachable')})</b>")
            self.lbl_t_health.setStyleSheet("color: #dc2626; font-size: 12px; padding: 4px;")

        conns = metrics.get("active_connections", metrics.get("connections", "--"))
        uptime = metrics.get("uptime", metrics.get("uptime_seconds", "--"))
        db_state = metrics.get("database_status", metrics.get("db", "Connected (Backend)"))

        self.lbl_t_conns.setText(f"Active Socket Connections: <b>{conns}</b>")
        self.lbl_t_uptime.setText(f"Server Process Uptime: <b>{uptime}</b>")
        self.lbl_t_db.setText(f"Database Connectivity State: <b>{db_state}</b>")

    # =========================================================================
    # Tab 4: Emergency Broadcasts
    # =========================================================================

    def _setup_broadcast_tab(self) -> None:
        layout = QVBoxLayout(self.broadcast_tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        desc = QLabel(
            "Dispatch live broadcast announcements to all active passenger desktop clients.\n"
            "Alerts are routed through the server broadcast engine to UDP client listeners."
        )
        desc.setStyleSheet("color: #475569; font-size: 12px;")
        layout.addWidget(desc)

        # Form
        card = QFrame()
        card.setStyleSheet("background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 14px;")
        f_layout = QVBoxLayout(card)
        f_layout.setSpacing(10)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Announcement Category:"))
        self.broadcast_type_combo = QComboBox()
        self.broadcast_type_combo.addItems([
            "GENERAL ADVISORY",
            "DELAY NOTIFICATION",
            "PLATFORM ALTERATION",
            "TATKAL OPENING NOTICE",
            "CRITICAL EMERGENCY"
        ])
        self.broadcast_type_combo.setStyleSheet("padding: 6px; border: 1px solid #cbd5e1; border-radius: 4px;")
        type_row.addWidget(self.broadcast_type_combo, 1)
        f_layout.addLayout(type_row)

        f_layout.addWidget(QLabel("Broadcast Message Content:"))
        self.broadcast_msg_text = QTextEdit()
        self.broadcast_msg_text.setPlaceholderText("Compose message for passenger terminals (e.g. Train 12301 delayed by 25 mins due to fog)...")
        self.broadcast_msg_text.setStyleSheet("border: 1px solid #cbd5e1; border-radius: 4px; padding: 8px;")
        f_layout.addWidget(self.broadcast_msg_text)

        self.dispatch_btn = QPushButton("📢 Dispatch Live Broadcast to Clients")
        self.dispatch_btn.setCursor(Qt.PointingHandCursor)
        self.dispatch_btn.setStyleSheet("""
            QPushButton {
                background-color: #d35400;
                color: #ffffff;
                font-weight: bold;
                padding: 10px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #b94400; }
        """)
        self.dispatch_btn.clicked.connect(self._handle_dispatch_broadcast)
        f_layout.addWidget(self.dispatch_btn)

        layout.addWidget(card)

    def _handle_dispatch_broadcast(self) -> None:
        """Pre-flight check, confirmation modal, and broadcast dispatch via TCP."""
        msg = self.broadcast_msg_text.toPlainText().strip()
        alert_type = self.broadcast_type_combo.currentText()

        if not msg:
            QMessageBox.warning(self, "Validation Error", "Please provide announcement message content.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Live Broadcast",
            f"Are you sure you want to broadcast this {alert_type} to all passenger clients?\n\n'{msg}'",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        try:
            resp = self.tcp_client.admin_broadcast_alert(message=msg, alert_type=alert_type)
            if resp.get("success"):
                QMessageBox.information(self, "Broadcast Sent", "Live announcement dispatched successfully.")
                self.broadcast_msg_text.clear()
            else:
                QMessageBox.critical(self, "Broadcast Failed", resp.get("message", "Server rejected broadcast."))
        except Exception as e:
            QMessageBox.critical(self, "Network Failure", str(e))

    def refresh_all_admin_data(self) -> None:
        """Refreshes fleet tables and REST metrics simultaneously."""
        self.fetch_fleet()
        self._poll_telemetry()
