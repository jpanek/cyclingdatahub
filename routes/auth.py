# routes/auth.py
from flask import Blueprint, session, redirect, url_for, current_app, request
from config import USER_STRAVA_ATHLETE_ID
from functools import wraps
from urllib.parse import urlencode
import requests
from core.database import get_db_connection, save_db_user_profile
import json, os
from datetime import datetime

"""
strava responded with:
https://stats.cyclingdatahub.com/callback?state=&code=3e5c76e553f5c15ea3354ede2e379314358f234e&scope=read,activity:read_all
"""

auth_bp = Blueprint('auth', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('athlete_id'):
            # Redirect to the landing page if no session exists
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route('/force-login')
def force_login():
    """Simulates a successful Strava OAuth login."""
    session['athlete_id'] = USER_STRAVA_ATHLETE_ID
    return redirect(url_for('main.index'))

@auth_bp.route('/login')
def login():
    # Define the permissions we need
    # activity:read_all is usually what you want for a full history
    params = {
        'client_id': current_app.config['APP_STRAVA_CLIENT_ID'],
        'redirect_uri': url_for('auth.strava_callback', _external=True),
        'response_type': 'code',
        'scope': 'read,activity:read_all',
        'approval_prompt': 'auto'
    }
    strava_url = f"https://www.strava.com/oauth/authorize?{urlencode(params)}"
    
    """
    print("\n--- DEBUG STRAVA PARAMS ---")
    print(params)
    print("---------------------------\n")
    return f"Debug: {params}"
    """

    return redirect(strava_url)

@auth_bp.route('/callback')
def strava_callback():
    code = request.args.get('code')
    error = request.args.get('error')

    if error or not code:
        return f"Authorization failed: {error}", 400

    # 1. Exchange the temporary code for permanent tokens
    token_url = "https://www.strava.com/oauth/token"
    payload = {
        'client_id': current_app.config['APP_STRAVA_CLIENT_ID'],
        'client_secret': current_app.config['APP_STRAVA_CLIENT_SECRET'],
        'code': code,
        'grant_type': 'authorization_code'
    }

    response = requests.post(token_url, data=payload)
    token_data = response.json()

    if response.status_code != 200:
        return f"Token exchange failed: {token_data}", 400
    
    # -------------------------------------------------------------------------------------------
    # --- DEBUG: Save token_data to file ---
    log_file_path = os.path.join(current_app.config['BASE_PATH'], 'logs', 'test_token_data.log')
    try:
        with open(log_file_path, 'a') as f:
            f.write(f"\n--- Login at {datetime.now()} ---\n")
            json.dump(token_data, f, indent=4)
            f.write("\n")
    except Exception as e:
        print(f"Could not write token log: {e}")
    # -------------------------------------------------------------------------------------------

    # 2. Extract data from Strava response
    # Strava returns { "access_token": "...", "athlete": { "id": 123, "firstname": "..." }, ... }
    athlete_data = token_data.get('athlete')
    athlete_id = athlete_data.get('id')

    # 3. Save tokens and profile to DB using your existing function
    conn = get_db_connection()
    try:
        save_db_user_profile(conn, athlete_data, token_data)
        
        # 4. Log the user into the session
        session['athlete_id'] = athlete_id
    finally:
        conn.close()

    # Redirect to the main dashboard
    return redirect(url_for('main.index'))

@auth_bp.route('/logout')
def logout():
    """Clears the session."""
    session.clear()
    return redirect(url_for('main.index'))