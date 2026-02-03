# run_sync.py

from datetime import datetime
from config import REFRESH_USER_PROFILE, REFRESH_HISTORY
from core.database import (
    get_db_connection, get_db_user, save_db_user_profile, 
    get_db_latest_timestamp_for_athlete, save_db_activities
)
from core.strava_api import get_valid_access_token, fetch_athlete_data, fetch_activities_list
from core.processor import process_activity_metrics
import sys

def run_sync(athlete_id):

    conn = get_db_connection()
    try:

        user = get_db_user(conn, athlete_id)

        if user:
            athlete_name = f"{user['firstname']} {user['lastname']}"
            exists = True
        else:
            athlete_name = "New Athlete"
            exists = False

        print(f"\tAthlete: {athlete_name} ({athlete_id})")

        # 1. Get valid token (handles logic internally)
        tokens_dict = get_valid_access_token(conn, athlete_id)
        token = tokens_dict['access_token']
        
        # 2. Sync Profile if needed
        if not exists or REFRESH_USER_PROFILE:
            print(f"\t👤 Syncing User Profile: {athlete_id}")
            profile = fetch_athlete_data(token)
            save_db_user_profile(conn, profile, tokens_dict)

        # 3. Sync Activities
        is_new_user = False

        if REFRESH_HISTORY:
            print("\t🔄 Performing full history sync (Page 1)...")
            params = {"page": 1, "per_page": 200}
        else:
            after_ts = get_db_latest_timestamp_for_athlete(conn, athlete_id)
            
            #after_ts = after_ts - 345600 #look 12 hours behind

            if after_ts == 0:
                is_new_user = True
                print(f"\t🚀 New user, getting 200 last activities")
                params = {"per_page":200}
            else:
                readable = datetime.fromtimestamp(after_ts).strftime('%Y-%m-%d %H:%M:%S')
                print(f"\t🚀 Incremental sync: Activities after {readable}")
                params = {"after": after_ts, "per_page": 200}


        activities=None
        activities = fetch_activities_list(token, params)

        if activities:
            # 4. Save the new activities to database
            save_db_activities(conn, athlete_id, activities)
            print(f"\t✅ Loaded {len(activities)} activities.")

            activities_to_process = activities[:10] if is_new_user else activities

            # ------------------------ Fetch Activity streams (details) -----------------------
            if not REFRESH_HISTORY:
                print(f"\t🧬 Fetching high-res streams for {len(activities_to_process)} activities...")

                from core.strava_api import sync_activity_streams

                for activity in activities_to_process:
                    strava_id = activity['id']
                    activity_type = activity.get('type')
                    try:
                        # 1. Fetch the activity streams (details)
                        sync_activity_streams(conn,athlete_id,strava_id)

                        if activity_type in ['Ride','VirtualRide']:
                            # 2. Trigger calculation of metrics:
                            process_activity_metrics(strava_id, force=True)
                            print(f"\t  ✨ Analyticsl metrics calculated for {strava_id}")
                        else:
                            print(f"\t  ⏩ Skipping analytics for non-cycling activity: {activity_type}")

                    except Exception as stream_error:
                        print(f"\t  ⚠️ Could not sync streams for {strava_id}: {stream_error}")
            # ---------------------------------------------------------------------------------
        else:
            print("\t∅ No new activities to load.")

    except Exception as e:
        print(f"❌ CRITICAL ERROR: {str(e)}")
        raise e # Re-raise so Flask can catch it if needed
    finally:
        conn.close()

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

if __name__ == "__main__":
    
    print(f"\n{'='*80}")
    print(f"Sync started: {now_str()}")

    if len(sys.argv)>1:
        athlete_id = int(sys.argv[1])
    else:
        athlete_id = 12689416

    run_sync(athlete_id)

    print(f"Sync Finished: {now_str()}")
    print(f"{'='*80}\n")