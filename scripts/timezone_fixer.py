# core/timezone_fixer.py

from core.database import get_db_connection, run_query
from datetime import datetime

def heal_zwift_timezones(athlete_id):
    """
    Forcefully shifts VirtualRides from Indonesia Time (+6/7) 
    back to Prague Time (+1) based on a 6-hour offset.
    """
    conn = get_db_connection()
    # DEBUG: Check exactly where we are connected
    dsn = conn.get_dsn_parameters()
    print(f"DEBUG: Connected to {dsn.get('dbname')} on {dsn.get('host')}")

    try:
        with conn.cursor() as cur:
            # 1. Update the activities
            sql = """
                UPDATE activities 
                SET start_date_local = start_date_local - INTERVAL '6 hours'
                WHERE type ILIKE 'VirtualRide' 
                  AND start_date_local >= '2025-02-01'
                  AND EXTRACT(HOUR FROM start_date_local) >= 20;
            """
            cur.execute(sql)
            count = cur.rowcount
            
            # 2. Force mark for recalculation
            # This ensures the fitness chart actually moves the TSS
            recalc_sql = """
                UPDATE activities 
                SET needs_recalculation = TRUE 
                WHERE type ILIKE 'VirtualRide' 
                  AND start_date_local >= '2026-02-01';
            """
            cur.execute(recalc_sql)
            
            conn.commit()
            print(f"✅ Successfully healed {count} rides and marked for recalculation.")
            
    except Exception as e:
        conn.rollback()
        print(f"❌ Failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    # You can get your athlete_id from your config or DB
    MY_ATHLETE_ID = 12689416 
    heal_zwift_timezones(MY_ATHLETE_ID)