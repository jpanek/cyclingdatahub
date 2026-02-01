# core/strava_api.py

import requests
from datetime import datetime, timedelta
from config import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN

def refresh_strava_tokens(refresh_token):
    payload = {
        'client_id': STRAVA_CLIENT_ID,
        'client_secret': STRAVA_CLIENT_SECRET,
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
            # Return in the same format as the API response
            return {'access_token': access_token, 'refresh_token': refresh_token, 'expires_at': expires_at}
        
        print("\t🔄 Token expired. Refreshing...")
        tokens = refresh_strava_tokens(refresh_token)
    else:
        print("\t⚠️ User not in DB. Using config refresh token...")
        tokens = refresh_strava_tokens(STRAVA_REFRESH_TOKEN)

    save_db_user_tokens(conn, athlete_id, tokens)
    return tokens

def fetch_athlete_data(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    res = requests.get("https://www.strava.com/api/v3/athlete", headers=headers)
    res.raise_for_status()
    return res.json()

def fetch_activities_list(access_token, params):
    headers = {"Authorization": f"Bearer {access_token}"}
    res = requests.get("https://www.strava.com/api/v3/athlete/activities", headers=headers, params=params)
    res.raise_for_status()
    
    print(f"\t📊 Rate Limit: {res.headers.get('X-RateLimit-Limit')}")
    print(f"\t📈 Current Usage: {res.headers.get('X-ReadRateLimit-Usage')}")
    return res.json()
