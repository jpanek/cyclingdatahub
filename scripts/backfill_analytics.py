# scripts/backfill_analytics.py

import sys
import os
from datetime import datetime

# Add root to path so we can import core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.database import run_query
from core.processor import process_activity_metrics
import numpy as np


def sync_local_analytics():
    """
    Identifies activities that have stream data but no calculated analytics,
    and runs the processor on them locally.
    """
    # 1. Find IDs that have streams but are missing from the analytics table
    missing_analytics = run_query("""
            SELECT s.strava_id 
            FROM activity_streams s
            JOIN activities act ON s.strava_id = act.strava_id
            LEFT JOIN activity_analytics a ON s.strava_id = a.strava_id
            WHERE act.type IN ('Ride', 'VirtualRide')
            AND (
                a.strava_id IS NULL 
                OR a.training_stress_score IS NULL
                -- Always re-check the last 20 cycling activities found in the system
                OR s.strava_id IN (
                    SELECT strava_id FROM activities 
                    WHERE type IN ('Ride', 'VirtualRide') 
                    ORDER BY start_date_local DESC LIMIT 20
                )
            )
            ORDER BY act.start_date_local ASC
    """)

    if not missing_analytics:
        print("All cycling streams have already been analyzed. Nothing to do.")
        return

    count = len(missing_analytics)
    print(f"Found {count} cycling activities to analyze locally. Starting...")

    processed = 0
    for row in missing_analytics:
        sid = row['strava_id']
        
        #success = process_activity_metrics(sid, force=True)

        try:
            # This calls the function in core/processor.py we wrote earlier
            success = process_activity_metrics(sid, force=True)
            if success:
                processed += 1
                #print(f"[{processed}/{count}] Processed activity: {sid}")
        except Exception as e:
            print(f"Error processing activity {sid}: {e}")

    print(f"Finished. Locally analyzed {processed} activities.")

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"Analytics recalc started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    sync_local_analytics()

    print(f"Analytics recalc Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")