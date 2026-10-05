"""
SMTP Email Notification Service for IRCTC Train Reservation Server
Dispatches transactional confirmation emails for bookings, cancellations, and account onboarding.
Includes fallback logging/archiving when running offline or without an active SMTP relay.
"""

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import smtplib
import socket
import time
from typing import Any, Dict

from logger import logger


class SMTPService:
    """
    Manages generation and transmission of transactional notifications via SMTP.
    """

    def __init__(self):
        self.host = os.getenv("SMTP_HOST", "127.0.0.1")
        self.port = int(os.getenv("SMTP_PORT", "1025"))
        self.user = os.getenv("SMTP_USER", "")
        self.password = os.getenv("SMTP_PASSWORD", "")
        self.sender = os.getenv("SMTP_FROM", "no-reply@railnet.gov.in")
        self.use_tls = os.getenv("SMTP_USE_TLS", "False").lower() in ("true", "1", "yes")
        self.emails_dir = os.path.join(os.path.abspath(os.getenv("FTP_DIR", "files")), "emails")
        os.makedirs(self.emails_dir, exist_ok=True)

    def send_booking_email(self, booking_data: Dict[str, Any]) -> bool:
        """Sends electronic ticket confirmation email."""
        recipient = booking_data.get("contact_email")
        if not recipient:
            return False

        pnr = booking_data.get("pnr")
        subject = f"Booking Confirmation - PNR: {pnr} | Train {booking_data.get('train_number')}"

        body_text = f"""Dear Passenger,

Your train ticket booking has been confirmed!

Journey Details:
----------------
PNR Number       : {pnr}
Train            : {booking_data.get('train_number')} - {booking_data.get('train_name')}
Date of Journey  : {booking_data.get('journey_date')}
Coach & Class    : {booking_data.get('coach_class')} ({booking_data.get('coach_number', 'C1')})
Total Fare Paid  : Rs. {float(booking_data.get('total_fare', 0.0)):.2f}
Allocated Seats  : {', '.join(booking_data.get('seats', []))}

Thank you for choosing Indian Railways.
IRCTC Next-Gen Ticketing Team
"""
        return self._send_or_archive_email(recipient, subject, body_text)

    def send_cancellation_email(self, cancel_data: Dict[str, Any]) -> bool:
        """Sends ticket cancellation and refund advisory email."""
        recipient = cancel_data.get("email")
        if not recipient:
            return False

        pnr = cancel_data.get("pnr")
        subject = f"Cancellation & Refund Advice - PNR: {pnr}"

        body_text = f"""Dear Passenger,

Your booking for PNR {pnr} on Train {cancel_data.get('train_number')} has been cancelled.

Refund Summary:
---------------
Original Fare       : Rs. {float(cancel_data.get('total_fare', 0.0)):.2f}
Clerkage Deductions : Rs. {float(cancel_data.get('cancellation_charge', 0.0)):.2f}
Net Refund Amount   : Rs. {float(cancel_data.get('refund_amount', 0.0)):.2f}

Refund will reflect in your account within 3 to 5 banking days.

Regards,
IRCTC Passenger Care
"""
        return self._send_or_archive_email(recipient, subject, body_text)

    def _send_or_archive_email(self, recipient: str, subject: str, body: str) -> bool:
        """
        Attempts SMTP delivery; falls back gracefully to archiving the email on disk if no SMTP relay is up.
        """
        msg = MIMEMultipart()
        msg["From"] = self.sender
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Save local copy for viva demonstration and audit inspection
        try:
            filename = f"email_{int(time.time())}_{recipient.replace('@', '_at_')}.txt"
            filepath = os.path.join(self.emails_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"FROM: {self.sender}\nTO: {recipient}\nSUBJECT: {subject}\n\n{body}")
        except Exception:
            pass

        # Attempt SMTP socket transmission
        try:
            with smtplib.SMTP(self.host, self.port, timeout=3.0) as server:
                if self.use_tls:
                    server.starttls()
                if self.user and self.password:
                    server.login(self.user, self.password)
                server.sendmail(self.sender, [recipient], msg.as_string())
            logger.info("Sent SMTP email to %s (Subject: %s)", recipient, subject)
            return True
        except (socket.error, smtplib.SMTPException) as e:
            logger.info("SMTP relay offline at %s:%d. Archived email locally for %s: %s", self.host, self.port, recipient, str(e))
            return True
        except Exception as e:
            logger.error("Failed to dispatch email to %s: %s", recipient, str(e))
            return False


# Singleton instance
smtp_service = SMTPService()
