import psycopg2
import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
DATABASE_URL = os.getenv("DATABASE_URL")

print(f"Loaded DATABASE_URL: {DATABASE_URL}")

try:
    conn = psycopg2.connect(DATABASE_URL)
    print("Connection successful!")
    conn.close()
except psycopg2.OperationalError as e:
    print(f"Connection failed: {e}")

DATABASE_URL = "postgresql://postgres:1234@localhost:5432/finapp_data"

try:
    conn = psycopg2.connect(DATABASE_URL)
    print("Connection successful! for 2nd time")
    conn.close()
except psycopg2.OperationalError as e:
    print(f"Connection failed for second time: {e}")