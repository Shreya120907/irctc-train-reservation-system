"""
Booking Service for IRCTC Train Reservation Server
Provides atomic, concurrency-safe ticket reservations using PostgreSQL row-level locks (FOR UPDATE),
PNR generation, and triggers asynchronous UDP/FTP/SMTP notifications.
"""

from datetime import datetime, date
import random
import secrets
from typing import Any, Dict, List, Optional

from database.connection import get_connection
from logger import logger


class BookingService:
    """
    Manages atomic seat reservation transactions, PNR lookups, and booking history.
    """

    @classmethod
    def generate_pnr(cls, cur) -> str:
        """
        Generates a unique 10-digit Indian Railways standard PNR string (prefix 245-).
        """
        for _ in range(10):
            pnr = f"245{secrets.randbelow(10000000):07d}"
            cur.execute("SELECT 1 FROM bookings WHERE pnr = %s;", (pnr,))
            if not cur.fetchone():
                return pnr
        # Fallback timestamp-based PNR
        return f"245{int(datetime.now().timestamp()) % 10000000:07d}"

    @classmethod
    def book_ticket(
        cls,
        user_id: Optional[int],
        train_number_or_id: Any,
        journey_date: str,
        coach_class: str,
        passengers: List[Dict[str, Any]],
        contact_email: str = "",
        contact_phone: str = "",
        payment_gateway: str = "IRCTC iPay"
    ) -> Dict[str, Any]:
        """
        Executes atomic ticket reservation using row-level locking (SELECT ... FOR UPDATE).
        Prevents race conditions where two clients select the same seat simultaneously.
        """
        if not passengers:
            return {"status": "error", "code": "NO_PASSENGERS", "message": "At least one passenger is required."}

        try:
            j_date = datetime.strptime(journey_date, "%Y-%m-%d").date()
            if j_date < date.today():
                return {"status": "error", "code": "PAST_DATE", "message": "Journey date cannot be in the past."}
        except ValueError:
            return {"status": "error", "code": "INVALID_DATE", "message": "Invalid date format. Use YYYY-MM-DD."}

        coach_class = coach_class.strip().upper()

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    # 1. Resolve train ID
                    cur.execute(
                        "SELECT id, train_number, train_name FROM trains WHERE train_number = %s OR id::TEXT = %s;",
                        (str(train_number_or_id), str(train_number_or_id))
                    )
                    train = cur.fetchone()
                    if not train:
                        return {"status": "error", "code": "TRAIN_NOT_FOUND", "message": "Train not found."}

                    train_id = train["id"]

                    # 2. Resolve coach and seats
                    # Find candidate coach matching class
                    cur.execute(
                        "SELECT id, coach_number, base_fare FROM coaches WHERE train_id = %s AND class_type = %s LIMIT 1;",
                        (train_id, coach_class)
                    )
                    coach = cur.fetchone()
                    if not coach:
                        return {
                            "status": "error",
                            "code": "CLASS_UNAVAILABLE",
                            "message": f"Class {coach_class} not found on train {train['train_number']}."
                        }

                    coach_id = coach["id"]
                    base_fare = float(coach["base_fare"])

                    # 3. Identify and Lock Requested Seats
                    seat_ids_to_lock = []
                    passenger_seat_map = []

                    for idx, p in enumerate(passengers):
                        req_seat_num = str(p.get("seat_number", "")).strip()

                        if req_seat_num:
                            # Specific seat requested
                            cur.execute(
                                """
                                SELECT id, seat_number, berth_type
                                FROM seats
                                WHERE coach_id = %s AND seat_number = %s
                                FOR UPDATE;
                                """,
                                (coach_id, req_seat_num)
                            )
                            seat_record = cur.fetchone()
                        else:
                            # Auto-allocate next available seat
                            cur.execute(
                                """
                                SELECT s.id, s.seat_number, s.berth_type
                                FROM seats s
                                WHERE s.coach_id = %s
                                  AND s.id NOT IN (
                                      SELECT p2.seat_id
                                      FROM passengers p2
                                      JOIN bookings b2 ON p2.booking_id = b2.id
                                      WHERE b2.train_id = %s
                                        AND b2.journey_date = %s
                                        AND b2.status = 'CONFIRMED'
                                  )
                                ORDER BY s.id
                                LIMIT 1
                                FOR UPDATE;
                                """,
                                (coach_id, train_id, j_date)
                            )
                            seat_record = cur.fetchone()

                        if not seat_record:
                            return {
                                "status": "error",
                                "code": "SEAT_UNAVAILABLE",
                                "message": f"Seat {req_seat_num or 'Auto'} in class {coach_class} is not available."
                            }

                        seat_ids_to_lock.append(seat_record["id"])
                        passenger_seat_map.append((p, seat_record))

                    # 4. Strict Row-Lock Check: Ensure NONE of these seats are booked for this date
                    cur.execute(
                        """
                        SELECT s.seat_number
                        FROM passengers p
                        JOIN bookings b ON p.booking_id = b.id
                        JOIN seats s ON s.id = p.seat_id
                        WHERE b.train_id = %s
                          AND b.journey_date = %s
                          AND b.status = 'CONFIRMED'
                          AND p.seat_id = ANY(%s)
                        FOR UPDATE;
                        """,
                        (train_id, j_date, seat_ids_to_lock)
                    )
                    conflicts = cur.fetchall()
                    if conflicts:
                        conflict_seats = ", ".join(c["seat_number"] for c in conflicts)
                        conn.rollback()
                        logger.warning(
                            "Concurrent booking collision detected on train %s date %s for seats: %s",
                            train["train_number"], j_date, conflict_seats
                        )
                        return {
                            "status": "error",
                            "code": "SEAT_UNAVAILABLE",
                            "message": f"Seat(s) {conflict_seats} were just reserved by another client. Please select another seat."
                        }

                    # 5. Calculate Grand Total
                    passenger_count = len(passengers)
                    subtotal = base_fare * passenger_count
                    reservation_fee = 40.0 * passenger_count
                    gst = (subtotal + reservation_fee) * 0.05
                    grand_total = subtotal + reservation_fee + gst

                    # 6. Generate Unique PNR
                    pnr = cls.generate_pnr(cur)

                    # 7. Insert Booking Record
                    cur.execute(
                        """
                        INSERT INTO bookings (pnr, user_id, train_id, journey_date, status, total_amount)
                        VALUES (%s, %s, %s, %s, 'CONFIRMED', %s)
                        RETURNING id, pnr, created_at;
                        """,
                        (pnr, user_id, train_id, j_date, grand_total)
                    )
                    booking_row = cur.fetchone()
                    booking_id = booking_row["id"]

                    # 8. Insert Passenger Records
                    allocated_passengers = []
                    allocated_seats = []
                    for p_data, seat_rec in passenger_seat_map:
                        cur.execute(
                            """
                            INSERT INTO passengers (booking_id, name, age, gender, coach_id, seat_id)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            RETURNING id;
                            """,
                            (
                                booking_id,
                                p_data.get("name", "Passenger"),
                                int(p_data.get("age", 25)),
                                p_data.get("gender", "Male"),
                                coach_id,
                                seat_rec["id"]
                            )
                        )
                        allocated_passengers.append({
                            "name": p_data.get("name"),
                            "age": p_data.get("age"),
                            "gender": p_data.get("gender"),
                            "coach": coach["coach_number"],
                            "seat_number": seat_rec["seat_number"],
                            "berth": seat_rec["berth_type"]
                        })
                        allocated_seats.append(f"{coach['coach_number']}-{seat_rec['seat_number']}")

                    # 9. Audit Log
                    cur.execute(
                        """
                        INSERT INTO audit_logs (user_id, action, description)
                        VALUES (%s, 'BOOK_TICKET', %s);
                        """,
                        (user_id, f"PNR {pnr} confirmed for train {train['train_number']} ({passenger_count} seats)")
                    )

            logger.info("Atomic reservation committed: PNR=%s, Train=%s, Seats=%s", pnr, train["train_number"], allocated_seats)

            booking_dict = {
                "pnr": pnr,
                "train_number": train["train_number"],
                "train_name": train["train_name"],
                "journey_date": journey_date,
                "coach_class": coach_class,
                "coach_number": coach["coach_number"],
                "passengers": allocated_passengers,
                "seats": allocated_seats,
                "total_fare": grand_total,
                "contact_email": contact_email,
                "contact_phone": contact_phone,
                "payment_gateway": payment_gateway,
                "status": "CONFIRMED"
            }

            # Asynchronous Protocol Hooks (Protected against failure)
            cls._trigger_notifications(booking_dict)

            return {
                "status": "success",
                "message": "Ticket reservation confirmed.",
                "pnr": pnr,
                "booking": booking_dict
            }

        except Exception as e:
            logger.error("Booking transaction aborted: %s", str(e))
            return {"status": "error", "code": "TRANSACTION_FAILED", "message": f"Reservation failed: {str(e)}"}

    @classmethod
    def get_booking(cls, pnr: str) -> Dict[str, Any]:
        """
        Enquires booking status, train information, and passenger list by PNR.
        """
        pnr = pnr.strip()
        if not pnr:
            return {"status": "error", "code": "INVALID_PNR", "message": "PNR required."}

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT b.id, b.pnr, b.journey_date, b.status, b.total_amount, b.created_at,
                               t.train_number, t.train_name,
                               u.username, u.email
                        FROM bookings b
                        JOIN trains t ON b.train_id = t.id
                        LEFT JOIN users u ON b.user_id = u.id
                        WHERE b.pnr = %s;
                        """,
                        (pnr,)
                    )
                    booking = cur.fetchone()
                    if not booking:
                        return {"status": "error", "code": "NOT_FOUND", "message": f"PNR '{pnr}' not found."}

                    # Fetch passengers
                    cur.execute(
                        """
                        SELECT p.name, p.age, p.gender, c.coach_number, c.class_type, s.seat_number, s.berth_type
                        FROM passengers p
                        JOIN coaches c ON p.coach_id = c.id
                        JOIN seats s ON p.seat_id = s.id
                        WHERE p.booking_id = %s;
                        """,
                        (booking["id"],)
                    )
                    passengers = cur.fetchall()

            return {
                "status": "success",
                "booking": {
                    "pnr": booking["pnr"],
                    "train_number": booking["train_number"],
                    "train_name": booking["train_name"],
                    "journey_date": booking["journey_date"].strftime("%Y-%m-%d"),
                    "status": booking["status"],
                    "chart_status": "CHART PREPARED" if booking["status"] == "CONFIRMED" else "CANCELLED",
                    "total_fare": float(booking["total_amount"]),
                    "booked_by": booking["username"],
                    "created_at": booking["created_at"].isoformat() if booking["created_at"] else None,
                    "passengers": [
                        {
                            "name": p["name"],
                            "age": p["age"],
                            "gender": p["gender"],
                            "coach": p["coach_number"],
                            "class": p["class_type"],
                            "seat_number": f"{p['coach_number']}-{p['seat_number']}",
                            "berth": p["berth_type"]
                        }
                        for p in passengers
                    ]
                }
            }
        except Exception as e:
            logger.error("Error retrieving PNR %s: %s", pnr, str(e))
            return {"status": "error", "code": "DB_ERROR", "message": str(e)}

    @classmethod
    def list_bookings(cls, user_id: Optional[int] = None, is_admin: bool = False) -> Dict[str, Any]:
        """
        Lists bookings for the authenticated user, or all bookings if is_admin is True.
        """
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    if is_admin or user_id is None:
                        cur.execute(
                            """
                            SELECT b.id, b.pnr, b.journey_date, b.status, b.total_amount, b.created_at,
                                   t.train_number, t.train_name,
                                   u.username
                            FROM bookings b
                            JOIN trains t ON b.train_id = t.id
                            LEFT JOIN users u ON b.user_id = u.id
                            ORDER BY b.created_at DESC
                            LIMIT 50;
                            """
                        )
                    else:
                        cur.execute(
                            """
                            SELECT b.id, b.pnr, b.journey_date, b.status, b.total_amount, b.created_at,
                                   t.train_number, t.train_name,
                                   u.username
                            FROM bookings b
                            JOIN trains t ON b.train_id = t.id
                            LEFT JOIN users u ON b.user_id = u.id
                            WHERE b.user_id = %s
                            ORDER BY b.created_at DESC;
                            """,
                            (user_id,)
                        )
                    booking_rows = cur.fetchall()

                    results = []
                    for b in booking_rows:
                        cur.execute(
                            """
                            SELECT p.name, p.age, c.coach_number, c.class_type, s.seat_number
                            FROM passengers p
                            JOIN coaches c ON p.coach_id = c.id
                            JOIN seats s ON p.seat_id = s.id
                            WHERE p.booking_id = %s;
                            """,
                            (b["id"],)
                        )
                        passengers = cur.fetchall()

                        results.append({
                            "pnr": b["pnr"],
                            "train_number": b["train_number"],
                            "train_name": b["train_name"],
                            "journey_date": b["journey_date"].strftime("%Y-%m-%d"),
                            "status": b["status"],
                            "total_fare": float(b["total_amount"]),
                            "booked_by": b["username"],
                            "coach_class": passengers[0]["class_type"] if passengers else "SL",
                            "passenger_count": len(passengers),
                            "passengers": [
                                {
                                    "name": p["name"],
                                    "seat_number": f"{p['coach_number']}-{p['seat_number']}"
                                }
                                for p in passengers
                            ]
                        })

            return {"status": "success", "bookings": results, "count": len(results)}
        except Exception as e:
            logger.error("Error listing bookings: %s", str(e))
            return {"status": "error", "code": "DB_ERROR", "message": str(e)}

    @classmethod
    def _trigger_notifications(cls, booking_dict: Dict[str, Any]) -> None:
        """Triggers UDP broadcast, FTP ticket generation, and SMTP email."""
        pnr = booking_dict.get("pnr")

        # 1. UDP Announcement
        try:
            from network.udp_server import udp_server
            udp_server.broadcast_announcement(
                message=f"Booking confirmed: Train {booking_dict['train_number']} (PNR: {pnr})",
                alert_type="BOOKING"
            )
        except Exception as e:
            logger.debug("UDP trigger notice: %s", str(e))

        # 2. FTP Ticket Generation
        try:
            from network.ftp_service import ftp_service
            ftp_service.generate_ticket_file(booking_dict)
        except Exception as e:
            logger.debug("FTP trigger notice: %s", str(e))

        # 3. SMTP Email
        try:
            from network.smtp_service import smtp_service
            if booking_dict.get("contact_email"):
                smtp_service.send_booking_email(booking_dict)
        except Exception as e:
            logger.debug("SMTP trigger notice: %s", str(e))
