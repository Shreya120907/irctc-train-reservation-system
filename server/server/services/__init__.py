"""
Services package for IRCTC Train Reservation Server.
"""
from .auth import AuthService
from .train import TrainService
from .booking import BookingService
from .cancellation import CancellationService
from .admin import AdminService

__all__ = ["AuthService", "TrainService", "BookingService", "CancellationService", "AdminService"]
