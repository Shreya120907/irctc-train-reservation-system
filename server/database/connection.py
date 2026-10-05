"""
Database Connection and Lifecycle Management for IRCTC Simulator
Provides parameterized psycopg connections, transactions, and schema setup.
"""

import os
import sys
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional, Tuple

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

# Load environment configuration
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "train_reservation")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

CONNECTION_STRING = (
    f"host={DB_HOST} port={DB_PORT} dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD}"
)


def get_db_config() -> Dict[str, Any]:
    """Returns database configuration dictionary."""
    return {
        "host": DB_HOST,
        "port": DB_PORT,
        "dbname": DB_NAME,
        "user": DB_USER,
        "password": DB_PASSWORD,
    }


@contextmanager
def get_connection(autocommit: bool = False) -> Generator[psycopg.Connection, None, None]:
    """
    Context manager yielding a psycopg connection with dict_row factory.
    Commits automatically on exit or rolls back if an exception occurs.
    """
    conn = psycopg.connect(
        CONNECTION_STRING,
        row_factory=dict_row,
        autocommit=autocommit,
        connect_timeout=10
    )
    try:
        yield conn
        if not autocommit and not conn.closed:
            conn.commit()
    except Exception:
        if not conn.closed:
            conn.rollback()
        raise
    finally:
        if not conn.closed:
            conn.close()


def test_connection() -> Tuple[bool, str]:
    """Tests connectivity to PostgreSQL server."""
    try:
        with psycopg.connect(CONNECTION_STRING, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
        return True, "Connected to PostgreSQL database successfully"
    except Exception as e:
        return False, str(e)


def init_database(schema_path: Optional[str] = None, seed_path: Optional[str] = None) -> Tuple[bool, str]:
    """
    Creates target database if not present, then runs schema.sql and seed.sql.
    """
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    schema_file = schema_path or os.path.join(curr_dir, "schema.sql")
    seed_file = seed_path or os.path.join(curr_dir, "seed.sql")

    # Step 1: Ensure database exists by connecting to 'postgres' maintenance DB
    maint_conn_str = f"host={DB_HOST} port={DB_PORT} dbname=postgres user={DB_USER} password={DB_PASSWORD}"
    try:
        with psycopg.connect(maint_conn_str, autocommit=True, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (DB_NAME,))
                exists = cur.fetchone()
                if not exists:
                    cur.execute(f'CREATE DATABASE "{DB_NAME}";')
    except Exception as e:
        # Maintenance connection might fail if user doesn't have create db, continue to check if DB exists
        pass

    # Step 2: Apply schema and seed
    try:
        with get_connection(autocommit=True) as conn:
            with conn.cursor() as cur:
                if os.path.exists(schema_file):
                    with open(schema_file, "r", encoding="utf-8") as f:
                        cur.execute(f.read())

                if os.path.exists(seed_file):
                    with open(seed_file, "r", encoding="utf-8") as f:
                        cur.execute(f.read())
        return True, f"Database '{DB_NAME}' initialized and seeded successfully."
    except Exception as e:
        return False, f"Database initialization error: {str(e)}"
