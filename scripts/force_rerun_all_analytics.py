# scripts/force_rerun_all_analytics.py
import config
from core.database import run_query
from core.processor import process_activity_metrics
from core.analysis import sync_daily_fitness

def get_db_all_athletes():
    """Fetches all registered athlete IDs."""
    res = run_query("SELECT athlete_id FROM users;")
    return [r['athlete_id'] for r in res]

def reset_athlete_data(athlete_id):
    """Wipes metrics and reset detection stats for a specific athlete only."""
    print(f"🧹 Clearing existing metrics for athlete {athlete_id}...")
    
    # 1. Delete analytics using a subquery since activity_analytics lacks athlete_id
    run_query("""
        DELETE FROM activity_analytics 
        WHERE strava_id IN (
            SELECT strava_id FROM activities WHERE athlete_id = %s
        )
    """, (athlete_id,))
    
    # 2. Delete fitness history (this table has athlete_id)
    run_query("DELETE FROM athlete_daily_metrics WHERE athlete_id = %s", (athlete_id,))
    
    # 3. Reset user detection baseline for a fresh chronological walk
    run_query("""
        UPDATE users 
        SET detected_ftp = NULL, 
            ftp_detected_at = NULL, 
            detected_max_hr = NULL, 
            hr_detected_at = NULL 
        WHERE athlete_id = %s
    """, (athlete_id,))

def reprocess_all():
    athlete_ids = get_db_all_athletes()
    print(f"👥 Found {len(athlete_ids)} athlete(s) to process.")

    for athlete_id in athlete_ids:
        # Step A: Reset this specific user
        reset_athlete_data(athlete_id)
        
        # Step B: Fetch activities chronologically from oldest to newest
        activities = run_query("""
            SELECT strava_id, start_date_local 
            FROM activities 
            WHERE athlete_id = %s AND type = ANY(%s)
            ORDER BY start_date_local ASC
        """, (athlete_id, config.ANALYTICS_ACTIVITIES))
        
        total = len(activities)
        if total == 0:
            print(f"⚠️ No matching activities found for athlete {athlete_id}.")
            continue

        print(f"🚀 Processing {total} activities for {athlete_id}...")

        # Step C: Re-calculate analytics (this builds the activity_analytics table)
        for i, activity in enumerate(activities):
            sid = activity['strava_id']
            # force=True ignores the 'exists' check since we just deleted the rows
            process_activity_metrics(sid, force=True)
            
            if i % 100 == 0 or i == total - 1:
                print(f"   ✅ [{i+1}/{total}] {activity['start_date_local']}")

        # Step D: Re-build Fitness (CTL/ATL/TSB) timeline
        # Start from the date of the first activity
        first_date_str = activities[0]['start_date_local'].strftime('%Y-%m-%d')
        print(f"⚖️ Reconstructing fitness curve from {first_date_str}...")
        
        days_processed = sync_daily_fitness(athlete_id, first_date_str)
        print(f"📈 {athlete_id}: {days_processed} days calculated.")

    print("\n🏆 Global re-processing complete.")

if __name__ == "__main__":
    reprocess_all()