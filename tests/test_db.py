import psycopg2
import os
from dotenv import load_dotenv
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

try:
    conn = psycopg2.connect(DATABASE_URL)
    print("Connection successful!")
    conn.close()
except psycopg2.OperationalError as e:
    print(f"Connection failed: {e}")

DATABASE_URL = "postgresql://postgres:1234@db:5432/finapp_data"

try:
    conn = psycopg2.connect(DATABASE_URL)
    print("Connection successful! for 2nd time")
    conn.close()
except psycopg2.OperationalError as e:
    print(f"Connection failed for second time: {e}")