# core/crawl_analytics.py

import sys
import os
from datetime import datetime

# Add root to path so we can import core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.database import get_db_connection, get_db_all_athletes, run_query
from core.processor import process_activity_metrics
from core.analysis import sync_daily_fitness
from core.queries import SQL_RECALC_QUEUE
from config import ANALYTICS_RECALC_SIZE


def sync_local_analytics(batch_size_per_user = 50, target_athlete_id=None):
    """
    Loop through users, and recalculate all analytics that needs recalc up to given batch size.
    Strictly in chronological order.
    """
    if target_athlete_id:
        # Just wrap the single ID in a list to keep the loop logic below
        athletes = [{'athlete_id': target_athlete_id, 'firstname': 'Targeted'}]
    else:
        athletes = get_db_all_athletes()

    if not athletes:
        print(" No users found in database")
        return

    for athlete in athletes:
        a_id = athlete['athlete_id']
        name = athlete['firstname']

        to_process = run_query(SQL_RECALC_QUEUE, (a_id, batch_size_per_user))

        if not to_process:
            print(f"\t{name} ({a_id}): Analytics are up to date.")
            continue
        
        print(f"\t{name} ({a_id}): Recomputing {len(to_process)} activities...")

        processed = 0
        first_date_in_batch = None
        try:
            for row in to_process:
                sid = row['strava_id']
                ride_date = row['start_date_local']
                
                # 3. Run the processor (FTP foundation)
                success = process_activity_metrics(sid, force=True)
                
                if success:
                    # 4. Mark as fixed so it leaves the queue
                    run_query(
                        "UPDATE activities SET needs_recalculation = FALSE WHERE strava_id = %s", 
                        (sid,)
                    )
                    processed += 1
                    if not first_date_in_batch or ride_date < first_date_in_batch:
                        first_date_in_batch = ride_date
            
            if processed > 0 and first_date_in_batch:
                print(f"\t✨ Batch complete. Syncing fitness from {first_date_in_batch.date()}...")
                sync_daily_fitness(a_id, first_date_in_batch)

        except Exception as user_err:
            print(f"  ⚠️ Error processing {name}: {user_err}")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"Analytics Recompute Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Process a batch per user
    sync_local_analytics(batch_size_per_user=ANALYTICS_RECALC_SIZE)

    print(f"Analytics Recompute Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")