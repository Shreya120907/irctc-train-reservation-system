-- =============================================================================
-- IRCTC-Style Train Reservation Simulator Seed Data
-- =============================================================================

-- Seed Users: Administrator & Passenger
INSERT INTO users (full_name, email, phone, username, password_hash, role)
VALUES
    ('System Administrator', 'admin@railway.gov.in', '9876543210', 'admin', '$2b$12$IN4/ZalyspYWLnnDwBFufug0UNr3tfAfguX13X7ysx/KWsB2p3d7u', 'ADMIN'),
    ('Rahul Sharma', 'passenger@example.com', '9811223344', 'passenger01', '$2b$12$2sCVbJU03SuUpKrQYwnlReBqK81N4ZyOZOI/Dd9xuT5XP2gEPGmnG', 'PASSENGER')
ON CONFLICT (username) DO NOTHING;

-- Seed Major Stations
INSERT INTO stations (station_code, station_name, city)
VALUES
    ('NDLS', 'New Delhi Railway Station', 'New Delhi'),
    ('BCT', 'Mumbai Central Railway Station', 'Mumbai'),
    ('HWH', 'Howrah Junction', 'Kolkata'),
    ('MAS', 'Chennai Central', 'Chennai'),
    ('SBC', 'KSR Bengaluru City', 'Bengaluru'),
    ('CNB', 'Kanpur Central', 'Kanpur'),
    ('ALD', 'Prayagraj Junction', 'Prayagraj'),
    ('DDU', 'Pt. Deen Dayal Upadhyaya Junction', 'Mughalsarai'),
    ('GKP', 'Gorakhpur Junction', 'Gorakhpur')
ON CONFLICT (station_code) DO NOTHING;

-- Seed Premium Express Trains
INSERT INTO trains (train_number, train_name, active)
VALUES
    ('12301', 'Howrah Rajdhani Express', TRUE),
    ('12951', 'Mumbai Tejas Rajdhani Express', TRUE),
    ('22436', 'Vande Bharat Express', TRUE)
ON CONFLICT (train_number) DO NOTHING;

-- Seed Routes for 12301 (HWH -> NDLS)
INSERT INTO routes (train_id, station_id, stop_order, arrival_time, departure_time, distance_km)
SELECT t.id, s.id, r.stop_order, r.arr::TIME, r.dep::TIME, r.km
FROM trains t
CROSS JOIN (
    VALUES
        ('HWH', 1, '16:50', '16:50', 0),
        ('DDU', 2, '00:45', '00:55', 680),
        ('ALD', 3, '02:30', '02:35', 833),
        ('CNB', 4, '04:40', '04:45', 1028),
        ('NDLS', 5, '10:05', '10:05', 1451)
) AS r(code, stop_order, arr, dep, km)
JOIN stations s ON s.station_code = r.code
WHERE t.train_number = '12301'
ON CONFLICT DO NOTHING;

-- Seed Routes for 12951 (BCT -> NDLS)
INSERT INTO routes (train_id, station_id, stop_order, arrival_time, departure_time, distance_km)
SELECT t.id, s.id, r.stop_order, r.arr::TIME, r.dep::TIME, r.km
FROM trains t
CROSS JOIN (
    VALUES
        ('BCT', 1, '17:00', '17:00', 0),
        ('NDLS', 2, '08:35', '08:35', 1384)
) AS r(code, stop_order, arr, dep, km)
JOIN stations s ON s.station_code = r.code
WHERE t.train_number = '12951'
ON CONFLICT DO NOTHING;

-- Seed Coaches for 12301 (1A, 2A, 3A, SL)
INSERT INTO coaches (train_id, coach_number, class_type, seat_count, base_fare)
SELECT t.id, c.coach_number, c.class_type, c.seat_count, c.fare
FROM trains t
CROSS JOIN (
    VALUES
        ('H1', '1A', 18, 3200.0),
        ('A1', '2A', 48, 2100.0),
        ('B1', '3A', 64, 1450.0),
        ('S1', 'SL', 72, 540.0)
) AS c(coach_number, class_type, seat_count, fare)
WHERE t.train_number = '12301'
ON CONFLICT DO NOTHING;

-- Seed Coaches for 12951 (1A, 2A, 3A)
INSERT INTO coaches (train_id, coach_number, class_type, seat_count, base_fare)
SELECT t.id, c.coach_number, c.class_type, c.seat_count, c.fare
FROM trains t
CROSS JOIN (
    VALUES
        ('H1', '1A', 18, 3350.0),
        ('A1', '2A', 48, 2250.0),
        ('B1', '3A', 64, 1550.0)
) AS c(coach_number, class_type, seat_count, fare)
WHERE t.train_number = '12951'
ON CONFLICT DO NOTHING;

-- Seed Seats for each Coach in 12301 and 12951
DO $$
DECLARE
    rec RECORD;
    i INT;
    berths TEXT[] := ARRAY['LB', 'MB', 'UB', 'LB', 'MB', 'UB', 'SL', 'SU'];
BEGIN
    FOR rec IN SELECT id, seat_count FROM coaches LOOP
        FOR i IN 1..rec.seat_count LOOP
            INSERT INTO seats (coach_id, seat_number, berth_type, status)
            VALUES (rec.id, i::TEXT, berths[((i - 1) % 8) + 1], 'AVAILABLE')
            ON CONFLICT DO NOTHING;
        END LOOP;
    END LOOP;
END $$;
