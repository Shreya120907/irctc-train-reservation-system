# IRCTC-Style Distributed Train Reservation Simulator

A modular, enterprise-grade, distributed train reservation system comprising a **PySide6 desktop frontend**, a **multithreaded Python backend server**, an integrated **networking suite (TCP, UDP, HTTP REST, FTP, SMTP)**, and a **PostgreSQL 14+ database layer with atomic concurrency controls**.

---

## 🏗️ System Architecture

```text
irctc_simulation/
├── client/                     # PySide6 Modern Desktop Frontend
│   ├── main.py                 # Application root & QStackedWidget coordinator
│   ├── ui/                     # UI Views (Login, Register, Dashboard, Search, Seats, Bookings, Admin)
│   └── network/                # Network abstraction clients (TCP, UDP listener, HTTP REST)
├── server/                     # Multithreaded Distributed Backend Server
│   ├── main.py                 # Server application orchestrator & signal supervisor
│   ├── tcp_server.py           # Multithreaded TCP socket listener (port 5000)
│   ├── client_handler.py       # Worker threads, JSON parser & session authorization
│   ├── logger.py               # Structured logger with automatic credential redaction
│   ├── services/               # Core business domain services
│   │   ├── auth.py             # User onboarding, bcrypt hashing, role authorization
│   │   ├── train.py            # Train search, route traversal, real-time seat matrices
│   │   ├── booking.py          # Atomic booking with row-level locks (FOR UPDATE)
│   │   ├── cancellation.py     # Cancellation lifecycle, refund policy, seat release
│   │   └── admin.py            # Fleet management, manifests & system telemetry
│   └── network/                # Protocol daemons
│       ├── udp_server.py       # Asynchronous UDP alert broadcaster (port 6000 -> 9999)
│       ├── http_server.py      # HTTP REST status & health API (port 8080)
│       ├── ftp_service.py      # E-ticket generator & embedded RFC-959 FTP daemon (port 2121)
│       └── smtp_service.py     # Transactional email dispatcher with local archiving (port 1025)
├── database/                   # PostgreSQL Data Layer
│   ├── connection.py           # Parameterized psycopg connection context manager
│   ├── schema.sql              # Relational DDL (10 tables, foreign keys & performance indices)
│   └── seed.sql                # Seed stations, premium trains (12301, 12951, 22436), coaches & users
├── tests/                      # Verification Test Suites
│   └── test_server.py          # 7-step comprehensive backend protocol & services test
├── mock_server.py              # Standalone lightweight mock TCP server for offline client testing
├── test_integration.py         # Client integration test suite
├── requirements.txt            # Dependency specification
└── .env.example                # Environment configuration template
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites & Environment Setup
Ensure you have **Python 3.10+** and **PostgreSQL 14+** installed.

```bash
# Clone or extract archive, then navigate into the directory:
cd irctc_simulation

# Create and activate a virtual environment:
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install all dependencies:
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
Create a `.env` file from `.env.example`:
```ini
# PostgreSQL Database Configuration
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=train_reservation
DB_USER=postgres
DB_PASSWORD=your_postgres_password

# Network Protocol Ports
TCP_HOST=0.0.0.0
TCP_PORT=5000
UDP_HOST=0.0.0.0
UDP_PORT=6000
UDP_BROADCAST_PORT=9999
HTTP_HOST=0.0.0.0
HTTP_PORT=8080
FTP_PORT=2121
SMTP_PORT=1025
```

### 3. Start the Master Backend Server
```bash
python server/main.py
```
*What happens:*
- Connects to PostgreSQL, automatically initializes the `train_reservation` database, executes `database/schema.sql` and `database/seed.sql`.
- Launches the multithreaded TCP reservation engine on port `5000`.
- Launches UDP broadcasting on port `6000` (transmitting to client port `9999`).
- Launches the HTTP REST telemetry service on `http://127.0.0.1:8080`.
- Launches the embedded RFC-959 FTP gateway on port `2121`.
- Initializes the transactional SMTP email dispatcher.

### 4. Launch the PySide6 Desktop GUI Client
In a separate terminal:
```bash
python client/main.py
```

### 5. Default Seed Accounts
- **Administrator**:
  - Username: `admin`
  - Password: `admin123`
- **Passenger**:
  - Username: `passenger01`
  - Password: `pass123`
*(Or click "Register" on the desktop client to onboard a new account)*

---

## 🧪 Running Automated Tests

Run the backend verification suite:
```bash
python tests/test_server.py
```
*Tests Bcrypt security, pre-flight input validation, UDP broadcasting, HTTP status endpoints, ERS e-ticket generation, FTP daemon transfers, SMTP email generation/archival, and concurrent TCP client stream dispatching.*

---

## 🔒 Concurrency & Reliability Highlights
1. **Row-Level Locking (`FOR UPDATE`)**: Prevents duplicate bookings by locking seat rows within atomic PostgreSQL transactions until commit or rollback.
2. **Zero Mock Data in Production**: All data flows strictly from PostgreSQL through parameterized `psycopg` queries.
3. **Graceful Teardown**: Intercepts `SIGINT`/`SIGTERM` to close client connections and sockets cleanly.
4. **Credential Sanitization**: Automatically masks passwords and tokens in all server logs.
