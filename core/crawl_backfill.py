# core/crawl_backfill.py

# cron setup: 
# 0,30 * * * * cd /home/ubuntu/apps/cycling_stats && ./venv/bin/python3 -u -m core.crawl_backfill >> logs/crawler_log.log 2>&1

import time, sys, os
from datetime import datetime, timedelta
from psycopg2.extras import RealDictCursor
from core.database import get_db_connection, get_db_all_athletes, run_query, save_db_activities
from core.strava_api import get_valid_access_token, fetch_activities_list
from run_sync import sync_single_activity
from core.queries import SQL_CRAWLER_BACKLOG
from config import CRAWL_BACKFILL_SIZE, CRAWL_HISTORY_DAYS, ANALYTICS_RECALC_SIZE

def crawl_backfill(batch_size_per_user=3, history_days=365, sleep_time=1):
    """
    Cycles through ALL users in the DB and backfills a few historical 
    cycling activities for each, respecting a 1-year hard stop.
    """

    # 1. Hard Stop: Only process rides from the last 365 days
    max_look_back_date = (datetime.now() - timedelta(days=history_days)).strftime('%Y-%m-%d %H:%M:%S')

    # 2. Get all athletes currently in our system
    athletes = get_db_all_athletes()

    if not athletes:
        print("∅ No users found in database.")
        return

    print(f"🕵️ Starting crawl for {len(athletes)} users...")

    for athlete in athletes:
        a_id = athlete['athlete_id']
        name = athlete['firstname']

        # ===============================================================================================================
        # 1. Fetch all activity summaries from history (Run only if not already completed):
        history_done = athlete.get('history_summaries_synced', False)
        if not history_done:
            res = run_query("SELECT MIN(start_date_local) as oldest FROM activities WHERE athlete_id = %s", (a_id,))
            db_oldest = res[0]['oldest'] if res and res[0]['oldest'] else None

            if db_oldest:
                print(f"\t📜 {name}: Oldest activity is {db_oldest.date()}. Fetching older summaries...")
                conn = get_db_connection()
                try:
                    tokens_dict = get_valid_access_token(conn, a_id)
                    before_ts = int(db_oldest.timestamp())
                    older_summaries = fetch_activities_list(tokens_dict['access_token'], {"before": before_ts, "per_page": 200})
                    
                    if older_summaries:
                        save_db_activities(conn, a_id, older_summaries)
                        print(f"\t✅ Added {len(older_summaries)} historical summaries.")
                    else:
                        # No more activities found on Strava -> We are finished forever.
                        print(f"\t🏁 Reached end of Strava history for {name}. Marking as synced.")
                        run_query("UPDATE users SET history_summaries_synced = TRUE WHERE athlete_id = %s", (a_id,))
                finally:
                    conn.close()
        # ===============================================================================================================

        to_process = run_query(SQL_CRAWLER_BACKLOG, (a_id, max_look_back_date, batch_size_per_user))

        if not to_process:
            print(f"\t✅ {name} ({a_id}): Fully caught up.")
            continue
        
        latest_date = to_process[-1]['start_date_local']
        date_str = latest_date.strftime('%Y-%m-%d') if hasattr(latest_date, 'strftime') else str(latest_date)
        print(f"\n🔄 {name} ({a_id}): Syncing {len(to_process)} activities (starting from {date_str})...")

        # 4. Process the batch for this user
        try:
            oldest_date = to_process[-1]['start_date_local']

            for row in to_process:
                s_id = row['strava_id']
                
                sync_single_activity(a_id, s_id, run_analytics=False)
                time.sleep(sleep_time)
            
            if oldest_date:
                safety_date = (oldest_date - timedelta(days=1)).strftime('%Y-%m-%d')
                from core.database import invalidate_analytics_from_date
                invalidate_analytics_from_date(a_id, safety_date)
                print(f"\n\t🚩Invalidated analytics for {name} ({a_id}) from {safety_date} forward.")

                from core.crawl_analytics import sync_local_analytics
                sync_local_analytics(batch_size_per_user=ANALYTICS_RECALC_SIZE,target_athlete_id=a_id)

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