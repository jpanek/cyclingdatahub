# core/strava_api.py

import requests
from datetime import datetime, timedelta
from config import APP_STRAVA_CLIENT_ID, APP_STRAVA_CLIENT_SECRET, USER_STRAVA_REFRESH_TOKEN, STRAVA_TIMEOUT

def print_rate_limits(res):
    """Prints rate limits if available; stays silent if not."""
    limit = res.headers.get('X-RateLimit-Limit')
    usage = res.headers.get('X-RateLimit-Usage')
    
    if limit and usage:
        try:
            l_15m, l_1d = limit.split(',')
            u_15m, u_1d = usage.split(',')
            print(f"\t📊 Rate limits: (15m) {u_15m}/{l_15m}, (1d) {u_1d}/{l_1d}")
        except (ValueError, IndexError):
            pass

def refresh_strava_tokens(refresh_token):
    payload = {
        'client_id': APP_STRAVA_CLIENT_ID,
        'client_secret': APP_STRAVA_CLIENT_SECRET,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token'
    }
    res = requests.post("https://www.strava.com/oauth/token", data=payload)
    res.raise_for_status()
    return res.json()

def get_valid_access_token(conn, athlete_id):
    """Returns the full tokens dict, refreshing if necessary."""
    from core.database import get_db_user_tokens, save_db_user_tokens
    
    row = get_db_user_tokens(conn, athlete_id)
    if row:
        access_token, refresh_token, expires_at = row
        if expires_at > datetime.now() + timedelta(minutes=5):
            # We have fresh tokens, no need to hit Srava API at all
            # Return in the same format as the API response
            return {'access_token': access_token, 'refresh_token': refresh_token, 'expires_at': expires_at}
        
        print("\t🔄 Token expired. Refreshing...")
        tokens = refresh_strava_tokens(refresh_token)
    else:
        print("\t⚠️ User not in DB. Using config refresh token...")
        tokens = refresh_strava_tokens(USER_STRAVA_REFRESH_TOKEN)

    save_db_user_tokens(conn, athlete_id, tokens)
    return tokens

def fetch_athlete_data(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    res = requests.get("https://www.strava.com/api/v3/athlete", headers=headers)
    res.raise_for_status()
    return res.json()

def fetch_activity_detail(access_token, activity_id):
    """
    Fetches a single activity's full summary/detail by its ID.
    Used for targeted updates from webhooks.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"https://www.strava.com/api/v3/activities/{activity_id}"
    
    res = requests.get(url, headers=headers, timeout=STRAVA_TIMEOUT)
    res.raise_for_status()
    
    print_rate_limits(res)
    return res.json()

def fetch_activities_list(access_token, params):
    headers = {"Authorization": f"Bearer {access_token}"}
    res = requests.get("https://www.strava.com/api/v3/athlete/activities", headers=headers, params=params, timeout=STRAVA_TIMEOUT)
    res.raise_for_status()
    
    print_rate_limits(res)
    return res.json()

def sync_activity_streams(conn, athlete_id, activity_id, force=False):
    """
    Orchestrates fetching streams from Strava and saving them to the DB.
    """
    from core.database import save_db_activity_stream
    
    # 0. Check if streams already exist locally
    if not force:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM activity_streams WHERE strava_id = %s", (activity_id,))
            if cur.fetchone():
                # Stream already in DB, skip API call
                print(f"\tStreams for activity {activity_id} already exists in activity_streams")
                return True

    # 1. Get valid token
    tokens = get_valid_access_token(conn, athlete_id)
    access_token = tokens['access_token']
    
    # 2. Define what we want to pull
    # Note: Using 'velocity_smooth' as that is Strava's internal key for speed
    stream_keys = "time,distance,velocity_smooth,heartrate,cadence,watts,temp,moving,altitude"
    url = f"https://www.strava.com/api/v3/activities/{activity_id}/streams"
    params = {
        "keys": stream_keys,
        "key_by_type": "true" 
    }
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        res = requests.get(url, headers=headers, params=params, timeout=STRAVA_TIMEOUT)
        res.raise_for_status()

        print_rate_limits(res)

        streams_data = res.json()

        # 3. Save to Database
        save_db_activity_stream(conn, activity_id, streams_data)
        #print(f"\tSaved streams for activity {activity_id}")
        return True

    except Exception as e:
        print(f"\t❌ Failed to sync streams for {activity_id}: {e}")
        return False
