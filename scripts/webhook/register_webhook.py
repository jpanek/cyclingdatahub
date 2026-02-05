# scripts/webhook/register_webhook.py

"""
USAGE INSTRUCTIONS:
-------------------
1. Ensure your VPS is running and the /ops/webhook route is accessible.
2. Run this script from your local Mac (in the project root):
   python3 scripts/webhook/register_webhook.py

3. If successful, Strava will perform an immediate handshake with your VPS.
4. Check your VPS logs (run_sync_log.log) to confirm: "WEBHOOK: Handshake successful."

note: You can only have ONE active subscription. If this fails with a 
'409 Conflict', use magage_webhook.py to delete the old one first.
"""

import os
import sys
import requests

# 1. Add the project root to sys.path so we can import config
# This goes up two levels from scripts/webhook/ to the root
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(ROOT_DIR)

try:
    from config import APP_STRAVA_CLIENT_ID, APP_STRAVA_CLIENT_SECRET, STRAVA_WEBHOOK_VERIFY_TOKEN
except ImportError:
    print("❌ Error: Could not find config.py. Make sure you're running this from the project structure.")
    sys.exit(1)

# The URL of your VPS endpoint
CALLBACK_URL = 'https://stats.cyclingdatahub.com/ops/webhook'

def register_subscription():
    url = "https://www.strava.com/api/v3/push_subscriptions"
    
    payload = {
        'client_id': APP_STRAVA_CLIENT_ID,
        'client_secret': APP_STRAVA_CLIENT_SECRET,
        'callback_url': CALLBACK_URL,
        'verify_token': STRAVA_WEBHOOK_VERIFY_TOKEN
    }

    print(f"🚀 Registering with Strava for ID: {APP_STRAVA_CLIENT_ID}...")
    response = requests.post(url, data=payload)
    
    if response.status_code in [200, 201]:
        print("✅ Success! Subscription created.")
        print(f"Response: {response.json()}")
    else:
        print(f"❌ Failed: {response.status_code}")
        print(f"Details: {response.text}")

if __name__ == "__main__":
    register_subscription()