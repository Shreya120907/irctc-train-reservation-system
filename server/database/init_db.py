import os
import psycopg

conn_str = "dbname=train_reservation user=postgres password=postgres host=127.0.0.1 port=5432"

try:
    with psycopg.connect(conn_str) as conn:
        with conn.cursor() as cur:
            schema_path = os.path.join("database", "schema.sql")
            seed_path = os.path.join("database", "seed.sql")
            
            print(f"Reading {schema_path}...")
            with open(schema_path, "r", encoding="utf-8") as f:
                cur.execute(f.read())
            
            print(f"Reading {seed_path}...")
            with open(seed_path, "r", encoding="utf-8") as f:
                cur.execute(f.read())
                
        conn.commit()
    print("\n>>> SUCCESS: Tables and Seed Data loaded perfectly! <<<")
except Exception as e:
    print(f"\nError: {e}")
