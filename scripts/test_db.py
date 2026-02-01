import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from config import DB_NAME, DB_USER, DB_HOST, DB_PORT

def test_connection():
    try:
        # Attempt to connect
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            host=DB_HOST,
            port=DB_PORT
        )
        
        # Create a cursor to execute a command
        cur = conn.cursor()
        cur.execute("SELECT version();")
        db_version = cur.fetchone()
        
        print("✅ Success! Connected to PostgreSQL.")
        print(f"Database version: {db_version[0]}")
        
        # Close the connection
        cur.close()
        conn.close()
        
    except Exception as e:
        print("❌ Error: Unable to connect to the database.")
        print(e)

if __name__ == "__main__":
    test_connection()