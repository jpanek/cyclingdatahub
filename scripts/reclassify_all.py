import sys
import os

# Ensure the project root is in the path so we can import core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.database import run_query
from core.analysis import classify_ride

def reclassify_all_activities():
    print("--- Starting Bulk Reclassification ---")
    
    # 1. Fetch the necessary data for all existing analytics
    # We join with activities to get distance, elevation, and moving_time
    sql_fetch = """
        SELECT 
            aa.strava_id,
            aa.intensity_score,
            aa.variability_index,
            aa.power_tiz,
            a.moving_time,
            a.distance,
            a.total_elevation_gain
        FROM activity_analytics aa
        JOIN activities a ON aa.strava_id = a.strava_id
    """
    
    activities = run_query(sql_fetch)
    if not activities:
        print("No activities found in activity_analytics.")
        return

    print(f"Found {len(activities)} activities to reclassify.")
    
    count = 0
    for act in activities:
        # 2. Map the DB row to the classifier dictionary
        metrics = {
            'if_score': act['intensity_score'],
            'vi_score': act['variability_index'],
            'duration_sec': act['moving_time'],
            'power_tiz': act['power_tiz'],
            'distance_m': act['distance'],
            'elevation_gain': act['total_elevation_gain']
        }
        
        # 3. Get the new label
        new_label = classify_ride(metrics)
        
        # 4. Update the database
        run_query(
            "UPDATE activity_analytics SET classification = %s WHERE strava_id = %s",
            (new_label, act['strava_id'])
        )
        
        count += 1
        if count % 10 == 0:
            print(f"Processed {count}/{len(activities)}...")

    print(f"--- Success! {count} activities updated. ---")

if __name__ == "__main__":
    reclassify_all_activities()