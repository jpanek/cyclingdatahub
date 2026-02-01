import requests
import json

# Paste the "access_token" you got from your previous test run here
ACCESS_TOKEN = "b4910f6326006408c936c8e309b82687b783fcc9"


def fetch_latest_activities():
    url = "https://www.strava.com/api/v3/athlete/activities"
    
    # We send the token in the 'Headers' now, not the payload
    headers = {
        'Authorization': f'Bearer {ACCESS_TOKEN}'
    }
    
    # We only want the last 5 activities to keep the screen clean
    params = {
        'per_page': 5
    }

    print(f"Checking Strava for latest activities...")
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        activities = response.json()
        print(f"✅ Success! Found {len(activities)} activities.")
        
        # Print the first one to see what it looks like
        # Define the path for the temporary dump
        dump_file = "logs/activities_dump.json"
        
        with open(dump_file, 'w') as f:
            json.dump(activities, f, indent=4)
            
        print(f"📁 Full data dumped to: {dump_file}")

    else:
        print(f"❌ Failed to fetch data.")
        print(f"Status: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    fetch_latest_activities()