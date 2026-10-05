"""
PySide6 UI Components for IRCTC-Style Train Reservation Simulator
"""
from .login import LoginWidget
from .register import RegisterWidget
from .dashboard import DashboardWidget
from .search import SearchWidget
from .seat_selection import SeatSelectionWidget
from .booking import BookingWidget
from .bookings import BookingsWidget
from .admin import AdminWidget

__all__ = [
    "LoginWidget",
    "RegisterWidget",
    "DashboardWidget",
    "SearchWidget",
    "SeatSelectionWidget",
    "BookingWidget",
    "BookingsWidget",
    "AdminWidget"
]
