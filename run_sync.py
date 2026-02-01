# run_sync.py

from datetime import datetime
from config import REFRESH_USER_PROFILE, REFRESH_HISTORY, MY_ATHLETE_ID
from core.database import (
    get_db_connection, get_db_user, save_db_user_profile, 
    get_db_latest_timestamp_for_athlete, save_db_activities
)
from core.strava_api import get_valid_access_token, fetch_athlete_data, fetch_activities_list
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
        if REFRESH_HISTORY:
            print("\t🔄 Performing full history sync (Page 1)...")
            params = {"page": 1, "per_page": 200}
        else:
            after_ts = get_db_latest_timestamp_for_athlete(conn, athlete_id)
            readable = datetime.fromtimestamp(after_ts).strftime('%Y-%m-%d %H:%M:%S')
            print(f"\t🚀 Incremental sync: Activities after {readable}")
            params = {"after": after_ts, "per_page": 200}

        activities=None
        #activities = fetch_activities_list(token, params)

        if activities:
            save_db_activities(conn, athlete_id, activities)
            print(f"\t✅ Loaded {len(activities)} activities.")
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
        athlete_id = MY_ATHLETE_ID

    run_sync(athlete_id)

    print(f"Sync Finished: {now_str()}")
    print(f"{'='*80}\n")