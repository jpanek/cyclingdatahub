# scripts/webhook/magage_webhook.py

"""
USAGE INSTRUCTIONS:
-------------------
1. To view current subscription status and get the ID:
   python3 scripts/webhook/magage_webhook.py

2. To delete an existing subscription (replace 123456 with the actual ID):
   python3 scripts/webhook/magage_webhook.py delete 123456

3. To register a new subscription (use the other script):
   python3 scripts/webhook/register_webhook.py
"""

import os
import sys
import requests

# Add the project root to sys.path so we can import config
# This goes up two levels from scripts/webhook/ to the root
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(ROOT_DIR)

try:
    from config import APP_STRAVA_CLIENT_ID, APP_STRAVA_CLIENT_SECRET
except ImportError:
    print("❌ Error: Could not find config.py.")
    sys.exit(1)

URL = "https://www.strava.com/api/v3/push_subscriptions"

def view_subscription():
    params = {
        'client_id': APP_STRAVA_CLIENT_ID, 
        'client_secret': APP_STRAVA_CLIENT_SECRET
    }
    r = requests.get(URL, params=params)
    print(f"🔍 Current Subscriptions for ID {APP_STRAVA_CLIENT_ID}:")
    print(r.text)

def delete_subscription(sub_id):
    delete_url = f"{URL}/{sub_id}"
    params = {
        'client_id': APP_STRAVA_CLIENT_ID, 
        'client_secret': APP_STRAVA_CLIENT_SECRET
    }
    r = requests.delete(delete_url, params=params)
    if r.status_code == 204:
        print(f"✅ Successfully deleted subscription ID: {sub_id}")
    else:
        print(f"❌ Failed to delete: {r.status_code}")
        print(r.text)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "delete":
        if len(sys.argv) > 2:
            delete_subscription(sys.argv[2])
        else:
            print("Usage: python manage_webhook.py delete <id>")
    else:
        view_subscription()