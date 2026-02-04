# core/crawl_backfill.py

# cron setup: 
# 0,30 * * * * cd /home/ubuntu/apps/cycling_stats && ./venv/bin/python3 -u -m core.crawl_backfill >> logs/crawler_log.log 2>&1

import time, sys, os
from datetime import datetime, timedelta
from psycopg2.extras import RealDictCursor
from core.database import get_db_connection
from core.strava_api import get_valid_access_token, sync_activity_streams
from core.processor import process_activity_metrics

def crawl_backfill(batch_size_per_user=3, sleep_time=2):
    """
    Cycles through ALL users in the DB and backfills a few historical 
    cycling activities for each, respecting a 1-year hard stop.
    """
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # 1. Hard Stop: Only process rides from the last 365 days
    one_year_ago = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d %H:%M:%S')
    print(one_year_ago)

    try:
        # 2. Get all athletes currently in our system
        cursor.execute("SELECT athlete_id, firstname FROM users")
        athletes = cursor.fetchall()

        if not athletes:
            print("∅ No users found in database.")
            return

        print(f"🕵️ Starting crawl for {len(athletes)} users...")

        for athlete in athletes:
            a_id = athlete['athlete_id']
            name = athlete['firstname']
            
            # 3. Find missing streams for THIS specific athlete
            query = """
                SELECT a.strava_id, a.type, a.start_date_local
                FROM activities a
                LEFT JOIN activity_streams s ON a.strava_id = s.strava_id
                WHERE a.athlete_id = %s 
                  --AND a.type IN ('Ride', 'VirtualRide')
                  AND a.start_date_local >= %s
                  AND s.strava_id IS NULL
                ORDER BY a.start_date_local DESC
                LIMIT %s
            """
            cursor.execute(query, (a_id, one_year_ago, batch_size_per_user))
            to_process = cursor.fetchall()

            if not to_process:
                print(f"  ✅ {name} ({a_id}): Fully caught up.")
                continue

            print(f"  🔄 {name} ({a_id}): Syncing {len(to_process)} activities...")

            # 4. Process the batch for this user
            try:
                #tokens = get_valid_access_token(conn, a_id) this is not really needed (done insite later)
                for row in to_process:
                    s_id = row['strava_id']
                    a_type = row['type']
                    a_date = row['start_date_local'].strftime('%Y-%m-%d')
                    sync_activity_streams(conn, a_id, s_id)

                    if a_type in ('Ride','VirtualRide'):
                        process_activity_metrics(s_id, force=True)
                        print(f"\t[{a_date}] Stream + Metrics synced for {a_type} ({s_id})")
                    else:
                        print(f"\t[{a_date}] Stream only synced for {a_type} ({s_id})")
                    time.sleep(sleep_time) # Pause between activities
            except Exception as user_err:
                print(f"⚠️ Error processing {name}: {user_err}")

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"Crawl Backfill Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Run a small batch for everyone
    crawl_backfill(batch_size_per_user=5)
    
    print(f"Crawl Backfill Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")