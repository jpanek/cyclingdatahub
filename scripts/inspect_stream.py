import os
import sys
import json
import requests

# Add root to path to access core modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import MY_ATHLETE_ID
from core.database import get_db_connection
from core.strava_api import get_valid_access_token

def inspect_activity_stream(activity_id):
    conn = get_db_connection()
    tokens = get_valid_access_token(conn, MY_ATHLETE_ID)
    access_token = tokens['access_token']

    print(f"--- Fetching streams for Activity: {activity_id} ---")

    stream_keys = "time,distance,altitude,heartrate,cadence,watts,temp,moving"
    url = f"https://www.strava.com/api/v3/activities/{activity_id}/streams"
    params = {
        "keys": stream_keys,
        "key_by_type": "true" 
    }
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        streams = res.json()

        # --- Logging to File ---
        log_filename = f"logs/stream_{activity_id}.json"
        with open(log_filename, "w") as f:
            json.dump(streams, f, indent=4)
        print(f"✅ Full raw data logged to: {log_filename}")

        # Summary for the console
        report = {}
        for key, stream_data in streams.items():
            report[key] = {
                "count": len(stream_data.get('data', [])),
                "sample": stream_data.get('data', [])[:3]
            }
        print("\n--- Summary ---")
        print(json.dumps(report, indent=4))
        
        if 'time' in streams and 'watts' in streams:
            print("\n--- Alignment Check ---")
            for i in range(3):
                print(f"T: {streams['time']['data'][i]}s | W: {streams['watts']['data'][i]}W")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    activity_id = 16704367490
    inspect_activity_stream(activity_id)