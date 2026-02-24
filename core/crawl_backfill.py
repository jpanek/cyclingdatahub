# core/crawl_backfill.py

# cron setup: 
# 0,30 * * * * cd /home/ubuntu/apps/cycling_stats && ./venv/bin/python3 -u -m core.crawl_backfill >> logs/crawler_log.log 2>&1

import time, sys, os
from datetime import datetime, timedelta
from psycopg2.extras import RealDictCursor
from core.database import get_db_connection, get_db_all_athletes, run_query
from core.strava_api import get_valid_access_token, sync_activity_streams
from run_sync import sync_single_activity
from core.processor import process_activity_metrics
from core.queries import SQL_CRAWLER_BACKLOG
from config import CRAWL_BACKFILL_SIZE, CRAWL_HISTORY_DAYS

def crawl_backfill(batch_size_per_user=3, history_days=365, sleep_time=2):
    """
    Cycles through ALL users in the DB and backfills a few historical 
    cycling activities for each, respecting a 1-year hard stop.
    """

    # 1. Hard Stop: Only process rides from the last 365 days
    one_year_ago = (datetime.now() - timedelta(days=history_days)).strftime('%Y-%m-%d %H:%M:%S')

    # 2. Get all athletes currently in our system
    athletes = get_db_all_athletes()

    if not athletes:
        print("∅ No users found in database.")
        return

    print(f"🕵️ Starting crawl for {len(athletes)} users...")

    for athlete in athletes:
        a_id = athlete['athlete_id']
        name = athlete['firstname']

        to_process = run_query(SQL_CRAWLER_BACKLOG, (a_id, one_year_ago, batch_size_per_user))

        if not to_process:
            print(f"\t✅ {name} ({a_id}): Fully caught up.")
            continue
        
        latest_date = to_process[-1]['start_date_local']
        date_str = latest_date.strftime('%Y-%m-%d') if hasattr(latest_date, 'strftime') else str(latest_date)
        print(f"\t🔄 {name} ({a_id}): Syncing {len(to_process)} activities (starting from {date_str})...")

        # 4. Process the batch for this user
        try:
            a_date = None

            for row in to_process:
                s_id = row['strava_id']
                a_date = row['start_date_local'].strftime('%Y-%m-%d')
                
                sync_single_activity(a_id, s_id)

                time.sleep(sleep_time) # Pause between activities
            
            if a_date:
                from core.database import invalidate_analytics_from_date
                invalidate_analytics_from_date(a_id, a_date)
                print(f"\t🚩Invalidated analytics for {name} ({a_id}) from {a_date} forward.\n")

        except Exception as user_err:
            print(f"⚠️ Error processing {name}: {user_err}")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"Crawl Backfill Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Run a small batch for everyone
    history_days = CRAWL_HISTORY_DAYS

    crawl_backfill(
        batch_size_per_user = CRAWL_BACKFILL_SIZE, 
        history_days = history_days
        )
    
    print(f"Crawl Backfill Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")