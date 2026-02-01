import sys
import os
import requests
import json
from datetime import datetime

# Tell Python to look in the root folder for config.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN

def test_strava_handshake():
    payload = {
        'client_id': STRAVA_CLIENT_ID,
        'client_secret': STRAVA_CLIENT_SECRET,
        'refresh_token': STRAVA_REFRESH_TOKEN,
        'grant_type': 'refresh_token'
    }
    
    print("🔄 Testing Strava handshake...")
    response = requests.post("https://www.strava.com/oauth/token", data=payload)
    
    # Current timestamp for the log entry
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = "logs/strava_tokens.log"
    
    if response.status_code == 200:
        data = response.json()
        
        # Append the result to the log file
        with open(log_file, 'a') as f:
            f.write(f"\n--- ENTRY: {now_str} ---\n")
            f.write(json.dumps(data, indent=4))
            f.write("\n")

        print(f"✅ Success! Entry added to {log_file}")
        return True
    else:
        with open(log_file, 'a') as f:
            f.write(f"\n--- ERROR: {now_str} ---\n")
            f.write(json.dumps(response.json(), indent=4))
            f.write("\n")
            
        print(f"❌ Handshake failed. Error logged to {log_file}")
        return False

if __name__ == "__main__":
    test_strava_handshake()