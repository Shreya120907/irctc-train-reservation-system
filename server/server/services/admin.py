"""
Admin Service for IRCTC Train Reservation Server
Provides train fleet management, route/schedule operations,
passenger manifest extraction, and administrative telemetry reports.
Strictly requires ADMIN role authorization.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from database.connection import get_connection
from logger import logger


class AdminService:
    """
    Administrative operations for fleet management, manifests, and reporting.
    """

    @classmethod
    def get_all_trains(cls) -> Dict[str, Any]:
        """
        Lists all trains with route summary and coach classes.
        """
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT 
                            t.id, t.train_number, t.train_name, t.active,
                            (SELECT s.station_code FROM routes r JOIN stations s ON r.station_id = s.id 
                             WHERE r.train_id = t.id ORDER BY r.stop_order ASC LIMIT 1) AS source,
                            (SELECT s.station_code FROM routes r JOIN stations s ON r.station_id = s.id 
                             WHERE r.train_id = t.id ORDER BY r.stop_order DESC LIMIT 1) AS destination,
                            (SELECT r.departure_time FROM routes r 
                             WHERE r.train_id = t.id ORDER BY r.stop_order ASC LIMIT 1) AS departure_time,
                            (SELECT r.arrival_time FROM routes r 
                             WHERE r.train_id = t.id ORDER BY r.stop_order DESC LIMIT 1) AS arrival_time
                        FROM trains t
                        ORDER BY t.train_number;
                        """
                    )
                    train_rows = cur.fetchall()

                    trains = []
                    for tr in train_rows:
                        # Fetch classes
                        cur.execute(
                            "SELECT DISTINCT class_type FROM coaches WHERE train_id = %s ORDER BY class_type;",
                            (tr["id"],)
                        )
                        classes = [c["class_type"] for c in cur.fetchall()]

                        dep = tr["departure_time"].strftime("%H:%M") if tr.get("departure_time") else "--:--"
                        arr = tr["arrival_time"].strftime("%H:%M") if tr.get("arrival_time") else "--:--"

                        trains.append({
                            "id": tr["id"],
                            "train_number": tr["train_number"],
                            "train_name": tr["train_name"],
                            "source": tr["source"] or "NDLS",
                            "destination": tr["destination"] or "BCT",
                            "departure_time": dep,
                            "arrival_time": arr,
                            "classes": classes or ["1A", "2A", "3A", "SL"],
                            "status": "ACTIVE" if tr["active"] else "CANCELLED"
                        })

            return {"status": "success", "trains": trains, "count": len(trains)}
        except Exception as e:
            logger.error("Admin fleet query failed: %s", str(e))
            return {"status": "error", "code": "DB_ERROR", "message": str(e)}

    @classmethod
    def add_train(cls, train_data: Dict[str, Any], user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Registers a new train, stops, coaches, and generates individual seat records.
        """
        train_num = str(train_data.get("train_number", "")).strip()
        train_name = str(train_data.get("train_name", "")).strip()
        source = str(train_data.get("source", "NDLS")).strip().upper()
        destination = str(train_data.get("destination", "BCT")).strip().upper()
        dep_time_str = str(train_data.get("departure_time", "06:00")).strip()
        arr_time_str = str(train_data.get("arrival_time", "22:00")).strip()

        if not train_num or not train_name:
            return {"status": "error", "code": "INVALID_INPUT", "message": "Train number and name are required."}

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    # 1. Insert Train
                    cur.execute(
                        """
                        INSERT INTO trains (train_number, train_name, active)
                        VALUES (%s, %s, TRUE)
                        RETURNING id;
                        """,
                        (train_num, train_name)
                    )
                    train_id = cur.fetchone()["id"]

                    # 2. Resolve stations or insert defaults
                    for code, name in [(source, f"{source} Central"), (destination, f"{destination} Junction")]:
                        cur.execute(
                            """
                            INSERT INTO stations (station_code, station_name, city)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (station_code) DO NOTHING;
                            """,
                            (code, name, code)
                        )

                    cur.execute("SELECT id FROM stations WHERE station_code = %s;", (source,))
                    src_id = cur.fetchone()["id"]
                    cur.execute("SELECT id FROM stations WHERE station_code = %s;", (destination,))
                    dst_id = cur.fetchone()["id"]

                    # 3. Insert Route
                    cur.execute(
                        """
                        INSERT INTO routes (train_id, station_id, stop_order, arrival_time, departure_time, distance_km)
                        VALUES (%s, %s, 1, %s::TIME, %s::TIME, 0),
                               (%s, %s, 2, %s::TIME, %s::TIME, 1200);
                        """,
                        (train_id, src_id, dep_time_str, dep_time_str, train_id, dst_id, arr_time_str, arr_time_str)
                    )

                    # 4. Insert Default Coach Configuration & Seats
                    coach_specs = [
                        ("H1", "1A", 18, 3000.0),
                        ("A1", "2A", 48, 2000.0),
                        ("B1", "3A", 64, 1400.0),
                        ("S1", "SL", 72, 500.0)
                    ]
                    berth_types = ["LB", "MB", "UB", "LB", "MB", "UB", "SL", "SU"]

                    for c_num, c_class, count, fare in coach_specs:
                        cur.execute(
                            """
                            INSERT INTO coaches (train_id, coach_number, class_type, seat_count, base_fare)
                            VALUES (%s, %s, %s, %s, %s)
                            RETURNING id;
                            """,
                            (train_id, c_num, c_class, count, fare)
                        )
                        coach_id = cur.fetchone()["id"]

                        # Insert seats
                        for s_idx in range(1, count + 1):
                            berth = berth_types[(s_idx - 1) % len(berth_types)]
                            cur.execute(
                                """
                                INSERT INTO seats (coach_id, seat_number, berth_type, status)
                                VALUES (%s, %s, %s, 'AVAILABLE');
                                """,
                                (coach_id, str(s_idx), berth)
                            )

                    # 5. Audit Log
                    cur.execute(
                        """
                        INSERT INTO audit_logs (user_id, action, description)
                        VALUES (%s, 'ADD_TRAIN', %s);
                        """,
                        (user_id, f"Added train {train_num} - {train_name} ({source} -> {destination})")
                    )

            logger.info("Admin registered new train: %s - %s", train_num, train_name)
            return {"status": "success", "message": f"Train {train_num} registered successfully.", "train_id": train_id}
        except Exception as e:
            logger.error("Failed to add train %s: %s", train_num, str(e))
            return {"status": "error", "code": "DB_ERROR", "message": str(e)}

    @classmethod
    def deactivate_train(cls, train_number_or_id: Any, reason: str = "", user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Deactivates a train schedule (cancelling future runs).
        """
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE trains
                        SET active = FALSE
                        WHERE train_number = %s OR id::TEXT = %s
                        RETURNING id, train_number, train_name;
                        """,
                        (str(train_number_or_id), str(train_number_or_id))
                    )
                    updated = cur.fetchone()
                    if not updated:
                        return {"status": "error", "code": "TRAIN_NOT_FOUND", "message": "Train not found."}

                    cur.execute(
                        """
                        INSERT INTO audit_logs (user_id, action, description)
                        VALUES (%s, 'DEACTIVATE_TRAIN', %s);
                        """,
                        (user_id, f"Deactivated train {updated['train_number']}: {reason}")
                    )

            logger.info("Train %s deactivated by admin: %s", updated["train_number"], reason)
            return {"status": "success", "message": f"Train {updated['train_number']} deactivated."}
        except Exception as e:
            logger.error("Error deactivating train: %s", str(e))
            return {"status": "error", "code": "DB_ERROR", "message": str(e)}

    @classmethod
    def get_manifest(cls, train_number_or_id: Any, journey_date: str) -> Dict[str, Any]:
        """
        Extracts passenger roster and seat allocation manifest for a train run.
        """
        try:
            j_date = datetime.strptime(journey_date, "%Y-%m-%d").date()
        except ValueError:
            return {"status": "error", "code": "INVALID_DATE", "message": "Date must be YYYY-MM-DD."}

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT 
                            b.pnr,
                            p.name,
                            p.age,
                            p.gender,
                            c.coach_number,
                            c.class_type,
                            s.seat_number,
                            s.berth_type,
                            b.status
                        FROM passengers p
                        JOIN bookings b ON p.booking_id = b.id
                        JOIN trains t ON b.train_id = t.id
                        JOIN coaches c ON p.coach_id = c.id
                        JOIN seats s ON p.seat_id = s.id
                        WHERE (t.train_number = %s OR t.id::TEXT = %s)
                          AND b.journey_date = %s
                          AND b.status = 'CONFIRMED'
                        ORDER BY c.coach_number, s.id;
                        """,
                        (str(train_number_or_id), str(train_number_or_id), j_date)
                    )
                    rows = cur.fetchall()

                    manifest = [
                        {
                            "pnr": r["pnr"],
                            "name": r["name"],
                            "age": r["age"],
                            "gender": r["gender"],
                            "coach": r["coach_number"],
                            "class": r["class_type"],
                            "seat_number": f"{r['coach_number']}-{r['seat_number']}",
                            "berth": r["berth_type"],
                            "status": r["status"]
                        }
                        for r in rows
                    ]

            return {"status": "success", "manifest": manifest, "count": len(manifest)}
        except Exception as e:
            logger.error("Error generating manifest: %s", str(e))
            return {"status": "error", "code": "DB_ERROR", "message": str(e)}

    @classmethod
    def get_system_stats(cls) -> Dict[str, Any]:
        """
        Computes system telemetry, revenue, and load statistics.
        """
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) AS count FROM users WHERE role = 'PASSENGER';")
                    users_count = cur.fetchone()["count"]

                    cur.execute("SELECT COUNT(*) AS count FROM trains WHERE active = TRUE;")
                    trains_count = cur.fetchone()["count"]

                    cur.execute("SELECT COUNT(*) AS count, COALESCE(SUM(total_amount), 0) AS revenue FROM bookings WHERE status = 'CONFIRMED';")
                    b_row = cur.fetchone()
                    confirmed_bookings = b_row["count"]
                    total_revenue = float(b_row["revenue"])

                    cur.execute("SELECT COUNT(*) AS count FROM bookings WHERE status = 'CANCELLED';")
                    cancelled_bookings = cur.fetchone()["count"]

            return {
                "status": "success",
                "stats": {
                    "registered_passengers": users_count,
                    "active_trains": trains_count,
                    "confirmed_bookings": confirmed_bookings,
                    "cancelled_bookings": cancelled_bookings,
                    "total_revenue": total_revenue,
                    "timestamp": datetime.now().isoformat()
                }
            }
        except Exception as e:
            logger.error("Error retrieving system statistics: %s", str(e))
            return {"status": "error", "code": "DB_ERROR", "message": str(e)}
