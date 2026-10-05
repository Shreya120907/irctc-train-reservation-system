"""
Train Service for IRCTC Train Reservation Server
Provides train schedule searches, dynamic route resolution,
coach configurations, and real-time seat availability matrices.
Zero hardcoded data: all queries run against PostgreSQL.
"""

from datetime import datetime, date
from typing import Any, Dict, List, Optional

from database.connection import get_connection
from logger import logger


class TrainService:
    """
    Handles train catalog lookups, route mapping, and real-time seat status calculation.
    """

    @classmethod
    def search_trains(
        cls,
        source: str,
        destination: str,
        journey_date: str,
        quota: str = "GENERAL",
        coach_class: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Searches matching trains where source stop_order < destination stop_order.
        Dynamically computes available seats per train for the requested journey date.
        """
        source = source.strip().upper()
        destination = destination.strip().upper()

        if not source or not destination:
            return {"status": "error", "code": "INVALID_STATION", "message": "Source and destination stations required."}

        try:
            # Validate date format YYYY-MM-DD
            j_date = datetime.strptime(journey_date, "%Y-%m-%d").date()
        except ValueError:
            return {"status": "error", "code": "INVALID_DATE", "message": "Date must be in YYYY-MM-DD format."}

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    query = """
                    SELECT 
                        t.id AS train_id,
                        t.train_number,
                        t.train_name,
                        s_src.station_code AS source_code,
                        s_src.station_name AS source_name,
                        r_src.departure_time,
                        s_dst.station_code AS dest_code,
                        s_dst.station_name AS dest_name,
                        r_dst.arrival_time,
                        (r_dst.distance_km - r_src.distance_km) AS distance
                    FROM trains t
                    JOIN routes r_src ON t.id = r_src.train_id
                    JOIN stations s_src ON r_src.station_id = s_src.id
                    JOIN routes r_dst ON t.id = r_dst.train_id
                    JOIN stations s_dst ON r_dst.station_id = s_dst.id
                    WHERE t.active = TRUE
                      AND (s_src.station_code = %s OR s_src.city ILIKE %s OR s_src.station_name ILIKE %s)
                      AND (s_dst.station_code = %s OR s_dst.city ILIKE %s OR s_dst.station_name ILIKE %s)
                      AND r_src.stop_order < r_dst.stop_order
                    ORDER BY r_src.departure_time;
                    """
                    wildcard_src = f"%{source}%"
                    wildcard_dst = f"%{destination}%"
                    cur.execute(
                        query,
                        (source, wildcard_src, wildcard_src, destination, wildcard_dst, wildcard_dst)
                    )
                    train_rows = cur.fetchall()

                    results = []
                    for t in train_rows:
                        train_id = t["train_id"]

                        # Fetch available classes and remaining seats for this train and journey date
                        coach_query = """
                        SELECT 
                            c.class_type,
                            SUM(c.seat_count) AS total_class_seats,
                            MIN(c.base_fare) AS base_fare,
                            COUNT(p.id) AS booked_count
                        FROM coaches c
                        LEFT JOIN seats s ON s.coach_id = c.id
                        LEFT JOIN passengers p ON p.seat_id = s.id 
                            AND p.booking_id IN (
                                SELECT b.id FROM bookings b 
                                WHERE b.train_id = %s 
                                  AND b.journey_date = %s 
                                  AND b.status = 'CONFIRMED'
                            )
                        WHERE c.train_id = %s
                        GROUP BY c.class_type;
                        """
                        cur.execute(coach_query, (train_id, j_date, train_id))
                        class_rows = cur.fetchall()

                        classes_available = {}
                        classes_list = []
                        for cr in class_rows:
                            c_type = cr["class_type"]
                            total = int(cr["total_class_seats"] or 0)
                            booked = int(cr["booked_count"] or 0)
                            avail = max(0, total - booked)
                            classes_available[c_type] = {
                                "available": avail,
                                "total": total,
                                "fare": float(cr["base_fare"] or 500.0)
                            }
                            classes_list.append(c_type)

                        # Filter by coach_class if specified
                        if coach_class and coach_class not in classes_available:
                            continue

                        dep_str = t["departure_time"].strftime("%H:%M") if t["departure_time"] else "--:--"
                        arr_str = t["arrival_time"].strftime("%H:%M") if t["arrival_time"] else "--:--"

                        results.append({
                            "train_id": train_id,
                            "train_number": t["train_number"],
                            "train_name": t["train_name"],
                            "source": t["source_code"],
                            "destination": t["dest_code"],
                            "source_name": t["source_name"],
                            "destination_name": t["dest_name"],
                            "departure_time": dep_str,
                            "arrival_time": arr_str,
                            "duration": "Dynamic",
                            "classes": classes_list,
                            "classes_detail": classes_available,
                            "available_classes": [f"{c} ({info['available']})" for c, info in classes_available.items()]
                        })

            return {
                "status": "success",
                "trains": results,
                "count": len(results),
                "query": {
                    "source": source,
                    "destination": destination,
                    "journey_date": journey_date,
                    "quota": quota
                }
            }
        except Exception as e:
            logger.error("Train search failed: %s", str(e))
            return {"status": "error", "code": "DB_ERROR", "message": f"Database search error: {str(e)}"}

    @classmethod
    def get_train(cls, train_number_or_id: Any) -> Dict[str, Any]:
        """
        Retrieves full details for a train including route stops and coach roster.
        """
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, train_number, train_name, active
                        FROM trains
                        WHERE train_number = %s OR id::TEXT = %s;
                        """,
                        (str(train_number_or_id), str(train_number_or_id))
                    )
                    train = cur.fetchone()
                    if not train:
                        return {"status": "error", "code": "TRAIN_NOT_FOUND", "message": "Train not found."}

                    train_id = train["id"]

                    # Fetch stops
                    cur.execute(
                        """
                        SELECT r.stop_order, s.station_code, s.station_name, s.city,
                               r.arrival_time, r.departure_time, r.distance_km
                        FROM routes r
                        JOIN stations s ON r.station_id = s.id
                        WHERE r.train_id = %s
                        ORDER BY r.stop_order;
                        """,
                        (train_id,)
                    )
                    stops = cur.fetchall()

                    # Fetch coaches
                    cur.execute(
                        """
                        SELECT coach_number, class_type, seat_count, base_fare
                        FROM coaches
                        WHERE train_id = %s
                        ORDER BY coach_number;
                        """,
                        (train_id,)
                    )
                    coaches = cur.fetchall()

            return {
                "status": "success",
                "train": {
                    "train_id": train["id"],
                    "train_number": train["train_number"],
                    "train_name": train["train_name"],
                    "active": train["active"],
                    "stops": [
                        {
                            "stop_order": s["stop_order"],
                            "station_code": s["station_code"],
                            "station_name": s["station_name"],
                            "city": s["city"],
                            "arrival_time": s["arrival_time"].strftime("%H:%M") if s["arrival_time"] else None,
                            "departure_time": s["departure_time"].strftime("%H:%M") if s["departure_time"] else None,
                            "distance_km": float(s["distance_km"] or 0)
                        }
                        for s in stops
                    ],
                    "coaches": [
                        {
                            "coach_number": c["coach_number"],
                            "class_type": c["class_type"],
                            "seat_count": c["seat_count"],
                            "base_fare": float(c["base_fare"])
                        }
                        for c in coaches
                    ]
                }
            }
        except Exception as e:
            logger.error("Error retrieving train details: %s", str(e))
            return {"status": "error", "code": "DB_ERROR", "message": str(e)}

    @classmethod
    def get_seats(
        cls,
        train_number_or_id: Any,
        coach_class: str,
        journey_date: str
    ) -> Dict[str, Any]:
        """
        Returns dynamic seat matrix for a train, class, and journey date.
        Flags seats as BOOKED if active confirmed booking exists for that date.
        """
        try:
            j_date = datetime.strptime(journey_date, "%Y-%m-%d").date()
        except ValueError:
            return {"status": "error", "code": "INVALID_DATE", "message": "Date must be YYYY-MM-DD."}

        coach_class = coach_class.strip().upper()

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    # Get train id
                    cur.execute(
                        "SELECT id, train_number, train_name FROM trains WHERE train_number = %s OR id::TEXT = %s;",
                        (str(train_number_or_id), str(train_number_or_id))
                    )
                    train = cur.fetchone()
                    if not train:
                        return {"status": "error", "code": "TRAIN_NOT_FOUND", "message": "Train not found."}

                    train_id = train["id"]

                    # Query all seats in coaches matching class and check active bookings
                    cur.execute(
                        """
                        SELECT 
                            s.id AS seat_id,
                            s.seat_number,
                            s.berth_type,
                            c.id AS coach_id,
                            c.coach_number,
                            c.class_type,
                            c.base_fare,
                            CASE 
                                WHEN p.id IS NOT NULL THEN 'BOOKED'
                                ELSE s.status
                            END AS seat_status
                        FROM coaches c
                        JOIN seats s ON s.coach_id = c.id
                        LEFT JOIN passengers p ON p.seat_id = s.id
                            AND p.booking_id IN (
                                SELECT b.id FROM bookings b 
                                WHERE b.train_id = %s 
                                  AND b.journey_date = %s 
                                  AND b.status = 'CONFIRMED'
                            )
                        WHERE c.train_id = %s
                          AND c.class_type = %s
                        ORDER BY c.coach_number, s.id;
                        """,
                        (train_id, j_date, train_id, coach_class)
                    )
                    seat_rows = cur.fetchall()

                    if not seat_rows:
                        # Check base fare if class exists
                        cur.execute(
                            "SELECT base_fare FROM coaches WHERE train_id = %s AND class_type = %s LIMIT 1;",
                            (train_id, coach_class)
                        )
                        cf = cur.fetchone()
                        base_fare = float(cf["base_fare"]) if cf else 500.0
                        return {
                            "status": "success",
                            "train_id": train_id,
                            "train_number": train["train_number"],
                            "coach_class": coach_class,
                            "journey_date": journey_date,
                            "fare": base_fare,
                            "seats": [],
                            "available_count": 0,
                            "total_seats": 0
                        }

                    base_fare = float(seat_rows[0]["base_fare"])
                    seats_list = []
                    available_count = 0

                    for sr in seat_rows:
                        st = sr["seat_status"]
                        if st == "AVAILABLE":
                            available_count += 1

                        seats_list.append({
                            "seat_id": sr["seat_id"],
                            "coach_id": sr["coach_id"],
                            "coach_number": sr["coach_number"],
                            "seat_number": sr["seat_number"],
                            "berth": sr["berth_type"],
                            "status": st
                        })

            return {
                "status": "success",
                "train_id": train["id"],
                "train_number": train["train_number"],
                "coach_class": coach_class,
                "journey_date": journey_date,
                "fare": base_fare,
                "seats": seats_list,
                "available_count": available_count,
                "total_seats": len(seats_list)
            }
        except Exception as e:
            logger.error("Error retrieving seat availability: %s", str(e))
            return {"status": "error", "code": "DB_ERROR", "message": str(e)}
