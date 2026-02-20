# run_sync.py

from datetime import datetime
from config import REFRESH_USER_PROFILE, REFRESH_HISTORY, ANALYTICS_RECALC_SIZE
from core.database import (
    get_db_connection, get_db_user, save_db_user_profile, 
    get_db_latest_timestamp_for_athlete, save_db_activities,
    get_db_all_athletes
)
from core.strava_api import get_valid_access_token, fetch_athlete_data, fetch_activities_list, fetch_activity_detail
from core.processor import process_activity_metrics
import sys

def sync_single_activity(athlete_id, activity_id):
    conn = get_db_connection()
    try:
        print(f"\n\t--- Targeted Sync: Activity {activity_id} for Athlete {athlete_id} ---")
        
        # 1. Get valid token
        tokens_dict = get_valid_access_token(conn, athlete_id)
        token = tokens_dict['access_token']
        
        # 2. Fetch the specific activity detail (Summary/Metadata)
        # This will get the new name/distance even if the activity is old
        activity = fetch_activity_detail(token, activity_id)
        
        if activity:
            # 3. Save it (save_db_activities expects a list, so we wrap it)
            save_db_activities(conn, athlete_id, [activity])
            print(f"\t✅ Activity {activity_id} metadata updated in DB.")

            # 4. Sync streams/metrics if it's a cycling activity
            from core.strava_api import sync_activity_streams
            sync_activity_streams(conn, athlete_id, activity_id)
            
            #5. process analytics
            process_activity_metrics(activity_id, force=True)
            print(f"\t✨ Analytics metrics recalculated for {activity_id}")

            #6. Invalidate all activity analytics afterwards
            from core.database import invalidate_analytics_from_date
            ride_date = activity.get('start_date_local')
            invalidate_analytics_from_date(athlete_id,ride_date)
            print(f"\t🚩Invalidated analytics for {athlete_id} from {ride_date} forward.")

            #7. actually run the analytics crawl:
            from core.crawl_analytics import sync_local_analytics
            sync_local_analytics(batch_size_per_user=ANALYTICS_RECALC_SIZE,target_athlete_id=athlete_id)

        else:
            print(f"\t⚠️ Could not find activity {activity_id} on Strava.")

    except Exception as e:
        print(f"❌ ERROR in single sync: {str(e)}")
    finally:
        conn.close()

def run_sync(athlete_id, athlete_name="Athlete"):

    conn = get_db_connection()
    try:

        print(f"\n\t--- Processing: {athlete_name} ({athlete_id}) ---")

        user = get_db_user(conn, athlete_id)

        if user:
            athlete_name = f"{user['firstname']} {user['lastname']}"
            exists = True
        else:
            athlete_name = "New Athlete"
            exists = False

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

            from config import NEW_USER_STREAMS_LOAD_COUNT

            activities_to_process = activities[:NEW_USER_STREAMS_LOAD_COUNT] if is_new_user else activities

            # ------------------------ Fetch Activity streams (details) -----------------------
            if not REFRESH_HISTORY or is_new_user:
                print(f"\t🧬 Fetching high-res streams for {len(activities_to_process)} activities...")

                from core.strava_api import sync_activity_streams

                activities_to_process.sort(key=lambda x: x['start_date_local'])
                earliest_date = activities[0]['start_date_local']


                for activity in activities_to_process:
                    strava_id = activity['id']
                    try:
                        # 1. Fetch the activity streams (details)
                        sync_activity_streams(conn,athlete_id,strava_id)
                        print(f"\t  ✨ Activity stream saved for {strava_id}")

                        process_activity_metrics(strava_id, force=True)
                        print(f"\t  ✨ Analyticsl metrics calculated for {strava_id}")

                    except Exception as stream_error:
                        print(f"\t  ⚠️ Could not sync streams for {strava_id}: {stream_error}")
                

                from core.database import invalidate_analytics_from_date
                invalidate_analytics_from_date(athlete_id, earliest_date)
                
                from core.crawl_analytics import sync_local_analytics
                sync_local_analytics(batch_size_per_user=ANALYTICS_RECALC_SIZE, target_athlete_id=athlete_id)
                print(f"\t🚩 Ripple effect finished for new batch.")
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

    if len(sys.argv) > 2:
        athlete_id = int(sys.argv[1])
        activity_id = int(sys.argv[2])
        sync_single_activity(athlete_id, activity_id)

    elif len(sys.argv)>1:
        athlete_id = int(sys.argv[1])
        run_sync(athlete_id, "Manual Trigger")
    else:
        athletes = get_db_all_athletes()
        print(f"Found {len(athletes)} registered athletes in database.")
        for athlete in athletes:
            run_sync(athlete['athlete_id'], athlete['firstname'])

    print(f"Sync Finished: {now_str()}")
    print(f"{'='*80}\n")