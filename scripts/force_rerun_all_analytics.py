# scripts/force_rerun_all_analytics.py
import config
from core.database import run_query, get_db_all_athletes
from core.processor import process_activity_metrics
from core.analysis import sync_daily_fitness

def reset_athlete_data(athlete_id, name):
    """Wipes metrics and reset detection stats for a specific athlete only."""
    print(f"🧹 Clearing existing metrics for {name} ({athlete_id})...")
    
    # 1. Delete analytics (joined via activities table)
    run_query("""
        DELETE FROM activity_analytics 
        WHERE strava_id IN (
            SELECT strava_id FROM activities WHERE athlete_id = %s
        )
    """, (athlete_id,))
    
    # 2. Delete fitness history
    run_query("DELETE FROM athlete_daily_metrics WHERE athlete_id = %s", (athlete_id,))
    
    # 3. Reset user detection baseline
    run_query("""
        UPDATE users 
        SET detected_ftp = NULL, 
            ftp_detected_at = NULL, 
            detected_max_hr = NULL, 
            hr_detected_at = NULL 
        WHERE athlete_id = %s
    """, (athlete_id,))

def reprocess_all():
    # Fetch from core/database.py
    athletes = get_db_all_athletes()
    print(f"👥 Found {len(athletes)} athlete(s) to process.")

    for athlete in athletes:
        a_id = athlete['athlete_id']
        name = athlete.get('firstname', 'Unknown')
        
        print(f"\n")
        # Step A: Reset this specific user
        reset_athlete_data(a_id, name)
        
        # Step B: Fetch activities chronologically
        activities = run_query("""
            SELECT a.strava_id, a.start_date_local 
            FROM activities a
            INNER JOIN activity_streams s ON a.strava_id = s.strava_id
            WHERE a.athlete_id = %s 
              --AND a.type = ANY(%s)
            ORDER BY a.start_date_local ASC
        """, (a_id, config.ANALYTICS_ACTIVITIES))
        
        total = len(activities)
        if total == 0:
            print(f"⚠️ No matching activities found for {name}.")
            continue

        print(f"🚀 Processing {total} activities for {name}...")

        # Step C: Re-calculate analytics
        for i, activity in enumerate(activities):
            sid = activity['strava_id']
            process_activity_metrics(sid, force=True)
            
            if i % 100 == 0 or i == total - 1:
                print(f"   ✅ [{i+1}/{total}] {activity['start_date_local']}")

        # Step D: Re-build Fitness (CTL/ATL/TSB) timeline
        first_date_str = activities[0]['start_date_local'].strftime('%Y-%m-%d')
        print(f"⚖️ Reconstructing fitness curve for {name} from {first_date_str}...")
        
        days_processed = sync_daily_fitness(a_id, first_date_str)
        print(f"📈 {name}: Fitness for {days_processed} days calculated.")

    print("\n🏆 Global re-processing complete.")

if __name__ == "__main__":
    reprocess_all()
