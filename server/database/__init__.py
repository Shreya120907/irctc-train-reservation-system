"""
Database package for IRCTC Train Reservation Simulator.
"""
from .connection import get_connection, test_connection, init_database, get_db_config

__all__ = ["get_connection", "test_connection", "init_database", "get_db_config"]
