# scripts/load_activities.py

import sys, os
import psycopg2
from psycopg2.extras import execute_batch, Json
import requests
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    DB_NAME, DB_USER, DB_HOST, DB_PORT, 
    STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN,
    REFRESH_USER_PROFILE, REFRESH_HISTORY
)

def get_db_connection():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        host=DB_HOST,
        port=DB_PORT
    )

def get_effective_tokens(conn, athlete_id):
    """
    Checks the DB for valid tokens. 
    Returns a dict with access_token.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT access_token, refresh_token, expires_at FROM users WHERE athlete_id = %s",
            (athlete_id,)
        )
        row = cur.fetchone()

    if row:
        access_token, refresh_token, expires_at = row
        # Check if token expires in the next 5 minutes to be safe
        if expires_at > datetime.now() + timedelta(minutes=5):
            print("ℹ️ Using valid access_token from Database.")
            return {'access_token': access_token, 'refresh_token': refresh_token, 'expires_at': expires_at}
        
        print("🔄 Token expired in DB. Refreshing via Strava API...")
        # Use the refresh_token from the DB to get a new one
        return refresh_strava_tokens(refresh_token)
    
    print("⚠️ User not found in DB. Falling back to config.py REFRESH_TOKEN...")
    from config import STRAVA_REFRESH_TOKEN
    return refresh_strava_tokens(STRAVA_REFRESH_TOKEN)

def refresh_strava_tokens(token_to_use):
    """Refreshes tokens using the provided refresh token."""
    payload = {
        'client_id': STRAVA_CLIENT_ID,
        'client_secret': STRAVA_CLIENT_SECRET,
        'refresh_token': token_to_use,
        'grant_type': 'refresh_token'
    }
    res = requests.post("https://www.strava.com/oauth/token", data=payload)
    res.raise_for_status()
    return res.json()

def upsert_user(conn, tokens):
    """Fetches current athlete and ensures they exist in the DB."""
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    res = requests.get("https://www.strava.com/api/v3/athlete", headers=headers)
    res.raise_for_status()
    athlete_data = res.json()

    with conn.cursor() as cur:
        sql = """
            INSERT INTO users (athlete_id, firstname, lastname, refresh_token, access_token, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (athlete_id) DO UPDATE SET
                refresh_token = EXCLUDED.refresh_token,
                access_token = EXCLUDED.access_token,
                expires_at = EXCLUDED.expires_at,
                updated_at = NOW();
        """
        cur.execute(sql, (
            athlete_data['id'],
            athlete_data.get('firstname'),
            athlete_data.get('lastname'),
            tokens['refresh_token'],
            tokens['access_token'],
            tokens['expires_at']
        ))
    conn.commit()
    print(f"✅ User {athlete_data.get('firstname')} synced.")
    return athlete_data['id']

def fetch_and_load_activities(conn, athlete_id, access_token):
    """Fetches activities and maps them to the activities table."""
    
    url = "https://www.strava.com/api/v3/athlete/activities"
    headers = {"Authorization": f"Bearer {access_token}"}

    if REFRESH_HISTORY:
        print("🔄 REFRESH_HISTORY is True: Performing page-based sync.")
        params = {
            "page": 1,      # Page 1 is the first 200
            "per_page": 200  # You want a small batch
            }
    else:
        after_ts = get_latest_timestamp_for_athlete(conn, athlete_id)

        readable_date = datetime.fromtimestamp(after_ts).strftime('%Y-%m-%d %H:%M:%S')
        print(f"🚀 Incremental sync: Fetching activities after {readable_date} (TS: {after_ts}).")
        params = {
                "after": after_ts,
                "per_page": 200
            }
    
    res = requests.get(url, headers=headers, params=params)
    res.raise_for_status()

    #print(res.headers)

    print(f"📊 Rate Limit (Short, Long): {res.headers.get('X-RateLimit-Limit')}")
    print(f"📈 Current Usage (Short, Long): {res.headers.get('X-ReadRateLimit-Usage')}")

    activities = res.json()
    
    insert_sql = """
        INSERT INTO activities (
            strava_id, athlete_id, name, type, start_date_local,
            distance, moving_time, elapsed_time, total_elevation_gain,
            average_speed, max_speed, average_watts, max_watts,
            weighted_average_watts, kilojoules, average_heartrate,
            max_heartrate, average_cadence, suffer_score,
            achievement_count, kudos_count, map_polyline, device_name, raw_json
        ) VALUES (
            %(id)s, %(athlete_id)s, %(name)s, %(type)s, %(start_date)s,
            %(dist)s, %(mov_t)s, %(ela_t)s, %(elev)s,
            %(avg_s)s, %(max_s)s, %(avg_w)s, %(max_w)s,
            %(weighted_w)s, %(kj)s, %(avg_hr)s,
            %(max_hr)s, %(avg_cad)s, %(suffer)s,
            %(achieve)s, %(kudos)s, %(poly)s, %(device)s, %(raw)s
        ) 
        ON CONFLICT (strava_id) DO UPDATE SET
            name = EXCLUDED.name,
            type = EXCLUDED.type,
            distance = EXCLUDED.distance,
            moving_time = EXCLUDED.moving_time,
            elapsed_time = EXCLUDED.elapsed_time,
            total_elevation_gain = EXCLUDED.total_elevation_gain,
            average_speed = EXCLUDED.average_speed,
            max_speed = EXCLUDED.max_speed,
            average_watts = EXCLUDED.average_watts,
            max_watts = EXCLUDED.max_watts,
            weighted_average_watts = EXCLUDED.weighted_average_watts,
            kilojoules = EXCLUDED.kilojoules,
            average_heartrate = EXCLUDED.average_heartrate,
            max_heartrate = EXCLUDED.max_heartrate,
            average_cadence = EXCLUDED.average_cadence,
            suffer_score = EXCLUDED.suffer_score,
            achievement_count = EXCLUDED.achievement_count,
            kudos_count = EXCLUDED.kudos_count,
            map_polyline = EXCLUDED.map_polyline,
            device_name = EXCLUDED.device_name,
            raw_json = EXCLUDED.raw_json,
            updated_at = NOW();
    """

    data_to_insert = []
    for a in activities:
        data_to_insert.append({
            'id': a['id'],
            'athlete_id': athlete_id,
            'name': a.get('name'),
            'type': a.get('type'),
            'start_date': a.get('start_date_local'),
            'dist': a.get('distance'),
            'mov_t': a.get('moving_time'),
            'ela_t': a.get('elapsed_time'),
            'elev': a.get('total_elevation_gain'),
            'avg_s': a.get('average_speed'),
            'max_s': a.get('max_speed'),
            'avg_w': a.get('average_watts'),
            'max_w': a.get('max_watts'),
            'weighted_w': a.get('weighted_average_watts'), # Fixed
            'kj': a.get('kilojoules'),
            'avg_hr': a.get('average_heartrate'),
            'max_hr': a.get('max_heartrate'),
            'avg_cad': a.get('average_cadence'),          # Was missing
            'suffer': a.get('suffer_score'),
            'achieve': a.get('achievement_count'),
            'kudos': a.get('kudos_count'),
            'poly': a.get('map', {}).get('summary_polyline'),
            'device': a.get('device_name'),               # Was missing
            'raw': Json(a)
        })

    with conn.cursor() as cur:
        execute_batch(cur, insert_sql, data_to_insert)
    
    conn.commit()
    print(f"✅ Loaded {len(data_to_insert)} activities.")

def user_exists(conn, athlete_id):
    """Check if the athlete is already in our database."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM users WHERE athlete_id = %s", (athlete_id,))
        return cur.fetchone() is not None

def get_latest_timestamp_for_athlete(conn, athlete_id):
    """Find the most recent ride specifically for THIS athlete."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT MAX(start_date_local) FROM activities WHERE athlete_id = %s", 
            (athlete_id,)
        )
        res = cur.fetchone()[0]
        # Return timestamp as integer, or 0 if they have no rides yet
        return int(res.timestamp()) if res else 0

if __name__ == "__main__":
    # You can set this as a variable for now
    MY_ATHLETE_ID = 12689416  # Replace with your actual Strava ID
    
    conn = get_db_connection()
    try:
        # 1. Get tokens efficiently
        tokens = get_effective_tokens(conn, MY_ATHLETE_ID)
        
        # 2. Only hit the /athlete API if the user is missing OR we explicitly want to refresh
        if not user_exists(conn, MY_ATHLETE_ID) or REFRESH_USER_PROFILE:
            print("👤 Syncing User Profile (API Hit)...")
            actual_id = upsert_user(conn, tokens)
        else:
            print("ℹ️ User exists. Skipping Profile API Hit.")
            actual_id = MY_ATHLETE_ID
        
        # 3. Load activities
        fetch_and_load_activities(conn, MY_ATHLETE_ID, tokens['access_token'])
        
    finally:
        conn.close()