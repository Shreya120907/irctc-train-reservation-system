"""
Authentication Service for IRCTC Train Reservation Server
Provides user registration, password hashing (bcrypt), login validation,
and server-side role authorization (PASSENGER vs ADMIN).
"""

import re
import secrets
from typing import Any, Dict, Optional, Tuple

import bcrypt

from database.connection import get_connection
from logger import logger


class AuthService:
    """
    Manages user lifecycle, secure password verification, and authorization.
    """

    EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_.-]{3,50}$")

    @classmethod
    def hash_password(cls, plain_password: str) -> str:
        """Hashes plaintext password with bcrypt and unique salt."""
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")

    @classmethod
    def verify_password(cls, plain_password: str, hashed_password: str) -> bool:
        """Verifies plaintext against stored bcrypt hash."""
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except Exception:
            return False

    @classmethod
    def register(
        cls,
        username: str,
        password: str,
        email: str,
        full_name: str,
        phone: str = "",
        role: str = "PASSENGER"
    ) -> Dict[str, Any]:
        """
        Registers a new user account in PostgreSQL with pre-flight sanitization.
        """
        username = username.strip()
        email = email.strip().lower()
        full_name = full_name.strip()
        phone = phone.strip()
        role = role.strip().upper()

        if role not in ("PASSENGER", "ADMIN"):
            role = "PASSENGER"

        # Pre-flight input validations
        if not full_name:
            return {"status": "error", "code": "INVALID_NAME", "message": "Full name is required."}

        if not cls.USERNAME_REGEX.match(username):
            return {
                "status": "error",
                "code": "INVALID_USERNAME",
                "message": "Username must be 3-50 alphanumeric characters (or _.-)."
            }

        if not cls.EMAIL_REGEX.match(email):
            return {"status": "error", "code": "INVALID_EMAIL", "message": "Invalid email address format."}

        if not password or len(password) < 6:
            return {
                "status": "error",
                "code": "WEAK_PASSWORD",
                "message": "Password must be at least 6 characters long."
            }

        password_hash = cls.hash_password(password)

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    # Check for collisions
                    cur.execute(
                        "SELECT username, email FROM users WHERE username = %s OR email = %s;",
                        (username, email)
                    )
                    existing = cur.fetchone()
                    if existing:
                        if existing["username"].lower() == username.lower():
                            return {
                                "status": "error",
                                "code": "USERNAME_EXISTS",
                                "message": f"Username '{username}' is already registered."
                            }
                        return {
                            "status": "error",
                            "code": "EMAIL_EXISTS",
                            "message": f"Email '{email}' is already associated with an account."
                        }

                    # Parameterized insertion
                    cur.execute(
                        """
                        INSERT INTO users (full_name, email, phone, username, password_hash, role)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id, full_name, email, phone, username, role, created_at;
                        """,
                        (full_name, email, phone, username, password_hash, role)
                    )
                    new_user = cur.fetchone()

            logger.info("User registered successfully: username=%s, role=%s", username, role)
            return {
                "status": "success",
                "message": "User registered successfully.",
                "user": {
                    "user_id": new_user["id"],
                    "username": new_user["username"],
                    "full_name": new_user["full_name"],
                    "email": new_user["email"],
                    "phone": new_user["phone"],
                    "role": new_user["role"],
                    "created_at": new_user["created_at"].isoformat() if new_user.get("created_at") else None
                }
            }
        except Exception as e:
            logger.error("Registration failed for username=%s: %s", username, str(e))
            return {"status": "error", "code": "DB_ERROR", "message": f"Database error during registration: {str(e)}"}

    @classmethod
    def login(cls, username: str, password: str) -> Dict[str, Any]:
        """
        Authenticates credentials against PostgreSQL bcrypt hash.
        """
        username = username.strip()
        if not username or not password:
            return {
                "status": "error",
                "code": "INVALID_INPUT",
                "message": "Username and password are required."
            }

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, full_name, email, phone, username, password_hash, role
                        FROM users
                        WHERE username = %s;
                        """,
                        (username,)
                    )
                    user = cur.fetchone()

            if not user or not cls.verify_password(password, user["password_hash"]):
                logger.warning("Failed login attempt for username=%s", username)
                return {
                    "status": "error",
                    "code": "AUTH_FAILED",
                    "message": "Invalid username or password."
                }

            token = secrets.token_hex(24)
            logger.info("User authenticated: username=%s, role=%s", username, user["role"])

            return {
                "status": "success",
                "message": "Login successful.",
                "token": token,
                "role": user["role"],
                "user": {
                    "user_id": user["id"],
                    "username": user["username"],
                    "full_name": user["full_name"],
                    "email": user["email"],
                    "phone": user["phone"],
                    "role": user["role"]
                }
            }
        except Exception as e:
            logger.error("Login database exception for username=%s: %s", username, str(e))
            return {"status": "error", "code": "DB_ERROR", "message": f"Authentication system error: {str(e)}"}

    @classmethod
    def authorize(cls, user_data: Optional[Dict[str, Any]], required_role: str = "PASSENGER") -> bool:
        """
        Server-side role-based authorization check.
        """
        if not user_data:
            return False
        user_role = user_data.get("role", "PASSENGER").upper()
        if required_role == "ADMIN" and user_role != "ADMIN":
            return False
        return True
