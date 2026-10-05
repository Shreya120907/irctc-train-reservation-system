"""
Modern Interactive Dashboard View for IRCTC-Style Train Reservation Simulator
- High-contrast card layouts, generous DPI-aware paddings
- Integrated "IRCTC AI RailSahayak" smart travel assistant & PNR predictor
- One-click Simulation Broadcaster (triggers real UDP packets into the live alert feed)
- Quick train status tracker & responsive recent activity table
"""

from typing import Any, Dict, Optional
import json
import random
import socket
from datetime import datetime

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QTextEdit
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


class DashboardWidget(QWidget):
    navigate_requested = Signal(str)  # 'search', 'bookings', 'admin', 'logout'
    enquire_pnr_requested = Signal(str)

    def __init__(
        self,
        tcp_client: TCPClient,
        http_client: HTTPClient,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.tcp_client = tcp_client
        self.http_client = http_client
        self.user_data: Dict[str, Any] = {}

        self._init_ui()

    def _init_ui(self) -> None:
        # Wrap everything in a smooth scroll area so screens with high DPI never clip
        scroll_wrapper = QScrollArea(self)
        scroll_wrapper.setWidgetResizable(True)
        scroll_wrapper.setStyleSheet("QScrollArea { border: none; background: #f8fafc; }")

        container = QWidget()
        container.setStyleSheet("background: #f8fafc;")
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(24, 20, 24, 24)
        main_layout.setSpacing(20)

        # -------------------------------------------------------------
        # 1. Premium Top Banner with Quick Stats & Pulse Indicators
        # -------------------------------------------------------------
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #092c4c, stop:0.6 #0f4c81, stop:1 #1e6091);
                border-radius: 12px;
                padding: 16px;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(20, 14, 20, 14)

        user_info_box = QVBoxLayout()
        self.welcome_label = QLabel("Welcome, Passenger")
        self.welcome_label.setStyleSheet("color: #ffffff; font-size: 20px; font-weight: 700; letter-spacing: 0.5px;")
        
        sub_info_layout = QHBoxLayout()
        self.role_badge = QLabel("Role: Passenger")
        self.role_badge.setStyleSheet("""
            background: rgba(255, 184, 77, 0.25);
            color: #ffbe76;
            font-size: 11px;
            font-weight: bold;
            padding: 3px 10px;
            border-radius: 10px;
            border: 1px solid rgba(255, 190, 118, 0.4);
        """)
        self.clock_badge = QLabel(datetime.now().strftime("%A, %d %b %Y"))
        self.clock_badge.setStyleSheet("color: #cbd5e1; font-size: 12px; margin-left: 8px;")
        sub_info_layout.addWidget(self.role_badge)
        sub_info_layout.addWidget(self.clock_badge)
        sub_info_layout.addStretch()

        user_info_box.addWidget(self.welcome_label)
        user_info_box.addLayout(sub_info_layout)
        header_layout.addLayout(user_info_box)

        header_layout.addStretch()

        # Telemetry & Refresh Actions
        status_box = QVBoxLayout()
        status_box.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.health_label = QLabel("● Gateway: Checking...")
        self.health_label.setStyleSheet("color: #38ef7d; font-size: 13px; font-weight: bold;")
        status_box.addWidget(self.health_label)

        btn_row = QHBoxLayout()
        self.sim_btn = QPushButton("📡 Broadcast Alert")
        self.sim_btn.setToolTip("Broadcast a simulated live rail alert over UDP port 9999")
        self.sim_btn.setCursor(Qt.PointingHandCursor)
        self.sim_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 153, 0, 0.25);
                color: #ffb703;
                border: 1px solid #ffb703;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background: rgba(255, 153, 0, 0.45); }
        """)
        self.sim_btn.clicked.connect(self._trigger_mock_broadcast)
        btn_row.addWidget(self.sim_btn)

        self.refresh_btn = QPushButton("↻ Refresh")
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.15);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.35);
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 0.28); }
        """)
        self.refresh_btn.clicked.connect(self.refresh_dashboard)
        btn_row.addWidget(self.refresh_btn)
        status_box.addLayout(btn_row)

        header_layout.addLayout(status_box)
        main_layout.addWidget(header_frame)

        # -------------------------------------------------------------
        # 2. Main 2-Column Grid (Shortcuts & AI vs. Broadcasts)
        # -------------------------------------------------------------
        grid_cols = QHBoxLayout()
        grid_cols.setSpacing(20)

        # ===== LEFT COLUMN =====
        left_col = QVBoxLayout()
        left_col.setSpacing(18)

        # Card A: Operational Shortcuts
        actions_card = QFrame()
        actions_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 16px;
            }
        """)
        actions_layout = QVBoxLayout(actions_card)
        actions_title = QLabel("⚡ Quick Operational Shortcuts")
        actions_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #0f172a;")
        actions_layout.addWidget(actions_title)

        grid_actions = QGridLayout()
        grid_actions.setSpacing(12)

        self.btn_book = QPushButton("🚆 Book Train Ticket")
        self.btn_book.setCursor(Qt.PointingHandCursor)
        self.btn_book.setStyleSheet(self._action_btn_style("#0284c7", "#0369a1"))
        self.btn_book.clicked.connect(lambda: self.navigate_requested.emit("search"))
        grid_actions.addWidget(self.btn_book, 0, 0)

        self.btn_my_bookings = QPushButton("📋 My Reservations")
        self.btn_my_bookings.setCursor(Qt.PointingHandCursor)
        self.btn_my_bookings.setStyleSheet(self._action_btn_style("#4f46e5", "#4338ca"))
        self.btn_my_bookings.clicked.connect(lambda: self.navigate_requested.emit("bookings"))
        grid_actions.addWidget(self.btn_my_bookings, 0, 1)

        self.btn_pnr = QPushButton("🔍 Live PNR Status")
        self.btn_pnr.setCursor(Qt.PointingHandCursor)
        self.btn_pnr.setStyleSheet(self._action_btn_style("#059669", "#047857"))
        self.btn_pnr.clicked.connect(lambda: self.pnr_input.setFocus())
        grid_actions.addWidget(self.btn_pnr, 1, 0)

        self.btn_admin = QPushButton("⚙ Admin Console")
        self.btn_admin.setCursor(Qt.PointingHandCursor)
        self.btn_admin.setStyleSheet(self._action_btn_style("#ea580c", "#c2410c"))
        self.btn_admin.clicked.connect(lambda: self.navigate_requested.emit("admin"))
        grid_actions.addWidget(self.btn_admin, 1, 1)

        actions_layout.addLayout(grid_actions)
        left_col.addWidget(actions_card)

        # Card B: Instant PNR Tracker
        pnr_card = QFrame()
        pnr_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 16px;
            }
        """)
        pnr_layout = QVBoxLayout(pnr_card)
        pnr_title = QLabel("🎫 Instant PNR Radar")
        pnr_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #0f172a;")
        pnr_layout.addWidget(pnr_title)

        pnr_input_row = QHBoxLayout()
        self.pnr_input = QLineEdit()
        self.pnr_input.setPlaceholderText("Enter 10-Digit PNR (e.g. 2459262847)")
        self.pnr_input.setMaxLength(10)
        self.pnr_input.setStyleSheet("""
            QLineEdit {
                min-height: 42px;
                padding: 6px 14px;
                border: 1.5px solid #cbd5e1;
                border-radius: 6px;
                font-size: 15px;
                font-weight: 700;
                color: #0f172a;
                background-color: #f8fafc;
                letter-spacing: 2px;
            }
            QLineEdit:focus { border: 2px solid #0284c7; background-color: #ffffff; }
        """)
        pnr_input_row.addWidget(self.pnr_input, 3)

        self.pnr_btn = QPushButton("Track Status")
        self.pnr_btn.setCursor(Qt.PointingHandCursor)
        self.pnr_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                min-height: 42px;
                padding: 6px 20px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #0369a1; }
        """)
        self.pnr_btn.clicked.connect(self._handle_quick_pnr)
        pnr_input_row.addWidget(self.pnr_btn, 1)
        pnr_layout.addLayout(pnr_input_row)

        self.pnr_result_label = QLabel("Enter your reservation PNR to pull live coach, train, and seat status.")
        self.pnr_result_label.setStyleSheet("color: #64748b; font-size: 12px; margin-top: 6px;")
        self.pnr_result_label.setWordWrap(True)
        pnr_layout.addWidget(self.pnr_result_label)

        left_col.addWidget(pnr_card)

        # Card C: IRCTC AI RailSahayak Assistant (Interactive Feature)
        ai_card = QFrame()
        ai_card.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f0fdf4, stop:1 #e0f2fe);
                border: 1px solid #bae6fd;
                border-radius: 10px;
                padding: 16px;
            }
        """)
        ai_layout = QVBoxLayout(ai_card)
        ai_header = QHBoxLayout()
        ai_title = QLabel("🤖 AI RailSahayak (Travel & PNR Predictor)")
        ai_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #0369a1;")
        ai_header.addWidget(ai_title)
        ai_header.addStretch()
        ai_badge = QLabel("GPT Rail Engine")
        ai_badge.setStyleSheet("font-size: 10px; font-weight: bold; color: #0284c7; background: #ffffff; padding: 2px 6px; border-radius: 4px;")
        ai_header.addWidget(ai_badge)
        ai_layout.addLayout(ai_header)

        self.ai_query_input = QLineEdit()
        self.ai_query_input.setPlaceholderText("Ask AI: 'Will my waitlist clear?' or 'Fastest train to Delhi?'")
        self.ai_query_input.setStyleSheet("""
            QLineEdit {
                min-height: 36px;
                padding: 4px 10px;
                font-size: 13px;
                border: 1px solid #93c5fd;
                border-radius: 6px;
                background-color: #ffffff;
            }
        """)
        self.ai_query_input.returnPressed.connect(self._handle_ai_query)

        ai_btn_row = QHBoxLayout()
        ai_ask_btn = QPushButton("Ask Assistant")
        ai_ask_btn.setCursor(Qt.PointingHandCursor)
        ai_ask_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-size: 12px;
                font-weight: bold;
                min-height: 32px;
                padding: 4px 14px;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #0369a1; }
        """)
        ai_ask_btn.clicked.connect(self._handle_ai_query)
        ai_btn_row.addWidget(self.ai_query_input)
        ai_btn_row.addWidget(ai_ask_btn)
        ai_layout.addLayout(ai_btn_row)

        self.ai_response_box = QLabel("RailSahayak ready. Type a query or test PNR confirmation probability.")
        self.ai_response_box.setStyleSheet("color: #334155; font-size: 12px; background: rgba(255,255,255,0.7); padding: 8px; border-radius: 6px;")
        self.ai_response_box.setWordWrap(True)
        ai_layout.addWidget(self.ai_response_box)

        left_col.addWidget(ai_card)
        grid_cols.addLayout(left_col, 5)

        # ===== RIGHT COLUMN: Live UDP Broadcast Feed =====
        right_col = QVBoxLayout()

        announcements_card = QFrame()
        announcements_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 16px;
            }
        """)
        ann_layout = QVBoxLayout(announcements_card)

        ann_header = QHBoxLayout()
        ann_title = QLabel("📢 Live Rail Bulletins (UDP 9999)")
        ann_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #ea580c;")
        ann_header.addWidget(ann_title)
        ann_header.addStretch()

        self.clear_ann_btn = QPushButton("Clear Feed")
        self.clear_ann_btn.setCursor(Qt.PointingHandCursor)
        self.clear_ann_btn.setStyleSheet("border: none; color: #64748b; font-size: 11px; font-weight: 600;")
        self.clear_ann_btn.clicked.connect(self._clear_announcements)
        ann_header.addWidget(self.clear_ann_btn)
        ann_layout.addLayout(ann_header)

        # Scrollable feed for live UDP alerts
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid #f1f5f9; background: #fafbfc; border-radius: 6px; }")

        self.ann_container = QWidget()
        self.ann_container_layout = QVBoxLayout(self.ann_container)
        self.ann_container_layout.setAlignment(Qt.AlignTop)
        self.ann_container_layout.setSpacing(10)

        self.no_ann_label = QLabel("Waiting for live broadcasts...\n(Click '📡 Broadcast Alert' above to push instant live updates)")
        self.no_ann_label.setStyleSheet("color: #94a3b8; font-style: italic; font-size: 12px; padding: 20px; text-align: center;")
        self.no_ann_label.setAlignment(Qt.AlignCenter)
        self.ann_container_layout.addWidget(self.no_ann_label)

        self.scroll_area.setWidget(self.ann_container)
        ann_layout.addWidget(self.scroll_area)

        right_col.addWidget(announcements_card)
        grid_cols.addLayout(right_col, 4)

        main_layout.addLayout(grid_cols)

        # -------------------------------------------------------------
        # 3. Dynamic Recent Bookings Overview Table
        # -------------------------------------------------------------
        bookings_card = QFrame()
        bookings_card.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 16px;
            }
        """)
        bk_layout = QVBoxLayout(bookings_card)

        bk_header = QHBoxLayout()
        bk_title = QLabel("🚆 Recent Reservation Portfolio (Hydrated from PostgreSQL)")
        bk_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #0f172a;")
        bk_header.addWidget(bk_title)
        bk_header.addStretch()

        view_all_btn = QPushButton("View All Bookings →")
        view_all_btn.setCursor(Qt.PointingHandCursor)
        view_all_btn.setStyleSheet("""
            QPushButton {
                background: none;
                border: none;
                color: #0284c7;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover { text-decoration: underline; color: #0369a1; }
        """)
        view_all_btn.clicked.connect(lambda: self.navigate_requested.emit("bookings"))
        bk_header.addWidget(view_all_btn)
        bk_layout.addLayout(bk_header)

        self.recent_table = QTableWidget(0, 6)
        self.recent_table.setHorizontalHeaderLabels([
            "PNR Number", "Train Details", "Travel Date", "Class", "Passengers", "Reservation Status"
        ])
        self.recent_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.recent_table.setAlternatingRowColors(True)
        self.recent_table.setMinimumHeight(150)
        self.recent_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                background-color: #ffffff;
                gridline-color: #f1f5f9;
                font-size: 13px;
                color: #0f172a;
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #092c4c;
                font-weight: bold;
                font-size: 12px;
                padding: 8px;
                border: none;
                border-bottom: 2px solid #e2e8f0;
            }
        """)
        bk_layout.addWidget(self.recent_table)

        main_layout.addWidget(bookings_card)

        # Set container into scroll area
        scroll_wrapper.setWidget(container)
        parent_layout = QVBoxLayout(self)
        parent_layout.setContentsMargins(0, 0, 0, 0)
        parent_layout.addWidget(scroll_wrapper)

    def _action_btn_style(self, bg: str, hover: str) -> str:
        return f"""
            QPushButton {{
                background-color: {bg};
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
                min-height: 42px;
                padding: 8px 14px;
                border-radius: 6px;
                text-align: center;
            }}
            QPushButton:hover {{ background-color: {hover}; }}
        """

    def set_user_context(self, user_info: Dict[str, Any]) -> None:
        self.user_data = user_info
        username = user_info.get("username", "Passenger")
        full_name = user_info.get("full_name", username)
        role = user_info.get("role", "passenger").capitalize()

        self.welcome_label.setText(f"Welcome, {full_name}")
        self.role_badge.setText(f"Portal Role: {role}")

        is_admin = (user_info.get("role") == "admin")
        self.btn_admin.setVisible(is_admin)

        self.refresh_dashboard()

    def refresh_dashboard(self) -> None:
        # Check HTTP Telemetry
        health_resp = self.http_client.check_health()
        if health_resp.get("success"):
            self.health_label.setText("● Gateway: 100% Operational")
            self.health_label.setStyleSheet("color: #38ef7d; font-size: 13px; font-weight: bold;")
        else:
            self.health_label.setText("● Gateway: Offline")
            self.health_label.setStyleSheet("color: #ef4444; font-size: 13px; font-weight: bold;")

        # Fetch Bookings over TCP
        try:
            resp = self.tcp_client.get_user_bookings()
            if resp.get("success"):
                bookings_list = resp.get("bookings", [])
                self._populate_recent_bookings(bookings_list)
            else:
                self.recent_table.setRowCount(0)
        except Exception:
            self.recent_table.setRowCount(0)

    def _populate_recent_bookings(self, bookings: list) -> None:
        self.recent_table.setRowCount(0)
        for row_idx, bk in enumerate(bookings[:6]):
            self.recent_table.insertRow(row_idx)
            pnr = str(bk.get("pnr", "N/A"))
            train_desc = f"{bk.get('train_number', '')} {bk.get('train_name', '')}".strip()
            date = str(bk.get("date") or bk.get("journey_date") or "N/A")
            cls = str(bk.get("coach_class", bk.get("class", "N/A")))
            passengers = str(len(bk.get("passengers", []))) if "passengers" in bk else str(bk.get("passenger_count", "1"))
            status = str(bk.get("status", "CNF")).upper()

            pnr_item = QTableWidgetItem(pnr)
            pnr_item.setTextAlignment(Qt.AlignCenter)
            pnr_item.setForeground(Qt.darkBlue)
            self.recent_table.setItem(row_idx, 0, pnr_item)

            self.recent_table.setItem(row_idx, 1, QTableWidgetItem(train_desc))

            date_item = QTableWidgetItem(date)
            date_item.setTextAlignment(Qt.AlignCenter)
            self.recent_table.setItem(row_idx, 2, date_item)

            cls_item = QTableWidgetItem(cls)
            cls_item.setTextAlignment(Qt.AlignCenter)
            self.recent_table.setItem(row_idx, 3, cls_item)

            pass_item = QTableWidgetItem(passengers)
            pass_item.setTextAlignment(Qt.AlignCenter)
            self.recent_table.setItem(row_idx, 4, pass_item)

            status_item = QTableWidgetItem(f"● {status}")
            status_item.setTextAlignment(Qt.AlignCenter)
            self.recent_table.setItem(row_idx, 5, status_item)

    def add_live_announcement(self, data: Dict[str, Any]) -> None:
        if self.no_ann_label.isVisible():
            self.no_ann_label.setVisible(False)

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #fffbeb;
                border-left: 5px solid #f59e0b;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)

        top_row = QHBoxLayout()
        badge = QLabel(f"[{data.get('type', 'ALERT')}]")
        badge.setStyleSheet("font-size: 11px; font-weight: bold; color: #b45309;")
        top_row.addWidget(badge)

        timestamp = QLabel(data.get("timestamp", datetime.now().strftime("%H:%M:%S")))
        timestamp.setStyleSheet("font-size: 11px; color: #78350f;")
        top_row.addWidget(timestamp)
        top_row.addStretch()
        layout.addLayout(top_row)

        msg = QLabel(data.get("message", ""))
        msg.setStyleSheet("color: #1e293b; font-size: 12px; font-weight: 500;")
        msg.setWordWrap(True)
        layout.addWidget(msg)

        self.ann_container_layout.insertWidget(0, card)

    def _clear_announcements(self) -> None:
        while self.ann_container_layout.count() > 1:
            item = self.ann_container_layout.takeAt(0)
            if item.widget() and item.widget() != self.no_ann_label:
                item.widget().deleteLater()
        self.no_ann_label.setVisible(True)

    def _handle_quick_pnr(self) -> None:
        pnr = self.pnr_input.text().strip()
        if not pnr or len(pnr) != 10 or not pnr.isdigit():
            QMessageBox.warning(self, "Validation Error", "Please provide a valid 10-digit numeric PNR.")
            return

        self.pnr_result_label.setText("Querying PNR status from server...")
        try:
            resp = self.tcp_client.pnr_enquiry(pnr)
            if resp.get("success"):
                booking = resp.get("booking", {})
                train = booking.get("train_name", booking.get("train_number", "Train"))
                status = booking.get("status", "CONFIRMED")
                date = booking.get("journey_date", booking.get("date", "N/A"))
                passengers = booking.get("passengers", [])
                p_summary = f"{len(passengers)} Passenger(s)" if passengers else "Allocated"

                self.pnr_result_label.setText(
                    f"✓ PNR {pnr}: {train} | Date: {date} | Status: {status} ({p_summary})"
                )
                self.pnr_result_label.setStyleSheet("color: #047857; font-weight: bold; font-size: 13px;")
            else:
                self.pnr_result_label.setText(f"✕ {resp.get('message', 'PNR not found on database.')}")
                self.pnr_result_label.setStyleSheet("color: #dc2626; font-size: 12px;")
        except Exception as e:
            self.pnr_result_label.setText(f"✕ Communication Error: {str(e)}")
            self.pnr_result_label.setStyleSheet("color: #dc2626; font-size: 12px;")

    def _handle_ai_query(self) -> None:
        """Simulates intelligent NLP Rail travel prediction and advice."""
        query = self.ai_query_input.text().strip()
        if not query:
            return

        query_lower = query.lower()
        if "pnr" in query_lower or "clear" in query_lower or "waitlist" in query_lower or "wl" in query_lower:
            prob = random.randint(86, 98)
            ans = f"🤖 RailSahayak: Based on historical passenger movement on this route, this ticket has a {prob}% probability of full confirmation prior to chart preparation."
        elif "delhi" in query_lower or "mumbai" in query_lower:
            ans = "🤖 RailSahayak: 12951 Mumbai Rajdhani offers the optimal transit time (15h 35m) with high pantry service reliability."
        elif "fast" in query_lower or "speed" in query_lower or "best" in query_lower:
            ans = "🤖 RailSahayak: Rajdhani & Shatabdi express services run at maximum authorized track speeds (130 km/h) with priority signal clearance."
        else:
            ans = f"🤖 RailSahayak: Query noted. Live telemetry shows optimal track availability and regular operating schedules for '{query}'."

        self.ai_response_box.setText(ans)
        self.ai_query_input.clear()

    def _trigger_mock_broadcast(self) -> None:
        """Sends a real UDP alert on port 9999 to test live announcements instantly."""
        messages = [
            "Train 12951 Mumbai Rajdhani arriving at Platform 3 (On Time).",
            "Platform Update: Train 12301 Howrah Express platform revised to Platform 5.",
            "Weather Advisory: Fog caution between NDLS and CNB; minor speed regulation in effect.",
            "Pantry Notice: Fresh evening snacks and hot tea service now boarding Coach B1 & B2."
        ]
        msg = random.choice(messages)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            payload = {
                "type": "BROADCAST",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "message": msg
            }
            sock.sendto(json.dumps(payload).encode("utf-8"), ("127.0.0.1", 9999))
            sock.close()
        except Exception as e:
            QMessageBox.information(self, "Broadcast Info", f"Simulated Alert: {msg}")