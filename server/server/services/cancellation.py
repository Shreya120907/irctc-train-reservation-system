"""
Cancellation Service for IRCTC Train Reservation Server
Manages booking cancellations, seat release, refund computations,
and audit trail persistence inside PostgreSQL transactions.
"""

from datetime import datetime, date
from typing import Any, Dict, Optional

from database.connection import get_connection
from logger import logger


class CancellationService:
    """
    Handles PNR cancellation workflow, ownership verification, and refund calculation.
    """

    CANCELLATION_FEE_PERCENT = 0.15  # 15% cancellation clerkage charge

    @classmethod
    def cancel_ticket(
        cls,
        pnr: str,
        user_id: Optional[int] = None,
        is_admin: bool = False,
        reason: str = "Passenger requested cancellation"
    ) -> Dict[str, Any]:
        """
        Executes cancellation transaction, releasing allocated seats back to the availability pool.
        """
        pnr = pnr.strip()
        if not pnr:
            return {"status": "error", "code": "INVALID_PNR", "message": "PNR is required."}

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    # 1. Lock and fetch booking row
                    cur.execute(
                        """
                        SELECT b.id, b.pnr, b.user_id, b.train_id, b.journey_date,
                               b.status, b.total_amount,
                               t.train_number, t.train_name,
                               u.email, u.full_name
                        FROM bookings b
                        JOIN trains t ON b.train_id = t.id
                        LEFT JOIN users u ON b.user_id = u.id
                        WHERE b.pnr = %s
                        FOR UPDATE;
                        """,
                        (pnr,)
                    )
                    booking = cur.fetchone()

                    if not booking:
                        return {"status": "error", "code": "NOT_FOUND", "message": f"PNR '{pnr}' does not exist."}

                    # 2. Authorization check: must be owner or admin
                    if not is_admin and user_id is not None:
                        if booking["user_id"] != user_id:
                            logger.warning("Unauthorized cancellation attempt for PNR %s by user %s", pnr, user_id)
                            return {
                                "status": "error",
                                "code": "UNAUTHORIZED",
                                "message": "You are not authorized to cancel this booking."
                            }

                    # 3. Check current status
                    if booking["status"] == "CANCELLED":
                        return {
                            "status": "error",
                            "code": "ALREADY_CANCELLED",
                            "message": f"PNR '{pnr}' has already been cancelled."
                        }

                    total_amount = float(booking["total_amount"])
                    cancellation_charge = round(total_amount * cls.CANCELLATION_FEE_PERCENT, 2)
                    refund_amount = max(0.0, round(total_amount - cancellation_charge, 2))

                    # 4. Update booking status
                    cur.execute(
                        "UPDATE bookings SET status = 'CANCELLED' WHERE id = %s;",
                        (booking["id"],)
                    )

                    # 5. Insert cancellation record
                    cur.execute(
                        """
                        INSERT INTO cancellations (booking_id, reason, refund_amount)
                        VALUES (%s, %s, %s)
                        RETURNING id, cancelled_at;
                        """,
                        (booking["id"], reason, refund_amount)
                    )
                    cancel_rec = cur.fetchone()

                    # 6. Audit Log
                    cur.execute(
                        """
                        INSERT INTO audit_logs (user_id, action, description)
                        VALUES (%s, 'CANCEL_TICKET', %s);
                        """,
                        (user_id, f"PNR {pnr} cancelled. Refund advice: Rs. {refund_amount:.2f}")
                    )

            logger.info("PNR %s cancelled successfully. Refund: %s", pnr, refund_amount)

            cancel_summary = {
                "pnr": pnr,
                "train_number": booking["train_number"],
                "train_name": booking["train_name"],
                "journey_date": booking["journey_date"].strftime("%Y-%m-%d"),
                "total_fare": total_amount,
                "cancellation_charge": cancellation_charge,
                "refund_amount": refund_amount,
                "email": booking.get("email"),
                "passenger_name": booking.get("full_name"),
                "cancelled_at": cancel_rec["cancelled_at"].isoformat() if cancel_rec else None
            }

            # Trigger asynchronous notifications
            cls._trigger_notifications(cancel_summary)

            return {
                "status": "success",
                "message": f"Ticket for PNR {pnr} cancelled successfully.",
                "pnr": pnr,
                "refund_amount": refund_amount,
                "cancellation_charge": cancellation_charge
            }

        except Exception as e:
            logger.error("Cancellation transaction failed for PNR %s: %s", pnr, str(e))
            return {"status": "error", "code": "DB_ERROR", "message": f"Cancellation error: {str(e)}"}

    @classmethod
    def _trigger_notifications(cls, cancel_summary: Dict[str, Any]) -> None:
        """Dispatches cancellation signals over UDP, FTP, and SMTP."""
        pnr = cancel_summary.get("pnr")

        # 1. UDP Announcement
        try:
            from network.udp_server import udp_server
            udp_server.broadcast_announcement(
                message=f"Seats released: PNR {pnr} cancelled on Train {cancel_summary['train_number']}",
                alert_type="SEAT_RELEASE"
            )
        except Exception as e:
            logger.debug("UDP cancellation notice: %s", str(e))

        # 2. FTP Cancellation Report
        try:
            from network.ftp_service import ftp_service
            ftp_service.generate_cancellation_report(cancel_summary)
        except Exception as e:
            logger.debug("FTP cancellation notice: %s", str(e))

        # 3. SMTP Cancellation Email
        try:
            from network.smtp_service import smtp_service
            if cancel_summary.get("email"):
                smtp_service.send_cancellation_email(cancel_summary)
        except Exception as e:
            logger.debug("SMTP cancellation notice: %s", str(e))
