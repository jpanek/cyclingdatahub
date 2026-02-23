# routes/auth.py
from flask import Blueprint, session, redirect, url_for, current_app, request
from config import USER_STRAVA_ATHLETE_ID, LOG_PATH
from functools import wraps
from urllib.parse import urlencode
import requests
from core.database import get_db_connection, save_db_user_profile
import json, os
from datetime import datetime
import subprocess
from run_sync import run_sync

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

"""
@auth_bp.route('/force-login')
def force_login():
    #Simulates a successful Strava OAuth login.
    session['athlete_id'] = USER_STRAVA_ATHLETE_ID
    return redirect(url_for('main.index'))
"""

@auth_bp.route('/login')
def login():
    print(f"[{datetime.now()}] INFO: Redirecting user to Strava for authorization.")

    params = {
        'client_id': current_app.config['APP_STRAVA_CLIENT_ID'],
        'redirect_uri': url_for('auth.strava_callback', _external=True),
        'response_type': 'code',
        'scope': 'read,activity:read_all',
        'approval_prompt': 'auto'
    }
    strava_url = f"https://www.strava.com/oauth/authorize?{urlencode(params)}"
    
    return redirect(strava_url)

@auth_bp.route('/callback')
def strava_callback():
    code = request.args.get('code')
    error = request.args.get('error')

    if error or not code:
        print(f"[{datetime.now()}] ERROR: Strava returned an error: {error}")
        return f"Authorization failed: {error}", 400
    
    if not code:
        print(f"[{datetime.now()}] WARNING: Callback reached without a code.")
        return "No code provided", 400

    print(f"[{datetime.now()}] INFO: Received code from Strava. Attempting token exchange.")

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
        print(f"[{datetime.now()}] ERROR: Token exchange failed with status {response.status_code}")
        return f"Token exchange failed: {token_data}", 400
    
    # -------------------------------------------------------------------------------------------
    # --- DEBUG: Save token_data to file ---
    """
    log_file_path = os.path.join(current_app.config['BASE_PATH'], 'logs', 'test_token_data.log')
    try:
        with open(log_file_path, 'a') as f:
            f.write(f"\n--- Login at {datetime.now()} ---\n")
            json.dump(token_data, f, indent=4)
            f.write("\n")
    except Exception as e:
        print(f"Could not write token log: {e}")
    """
    # -------------------------------------------------------------------------------------------

    # 2. Extract data from Strava response
    # Strava returns { "access_token": "...", "athlete": { "id": 123, "firstname": "..." }, ... }
    athlete_data = token_data.get('athlete')
    athlete_id = athlete_data.get('id')
    firstname = athlete_data.get('firstname', 'Athlete')

    # 3. Save tokens and profile to DB using your existing function
    conn = get_db_connection()
    try:
        is_new_user = save_db_user_profile(conn, athlete_data, token_data)
        session['athlete_id'] = athlete_id

        # ------------ NEW USER TIRGGER ACTIVITY LOAD -------------------
        if is_new_user:
            with open(LOG_PATH, "a") as log_file:
                log_file.write(f"\n[{datetime.now()}] 🚀 NEW USER REGISTERED: {firstname} ({athlete_id})\n")

            print(f"[{datetime.now()}] 🚀 NEW USER: Starting background sync for {firstname} ({athlete_id})...", flush=True)
            
            try:
                # Use the exact same subprocess logic as your webhook
                python_executable = os.path.join(current_app.config['BASE_PATH'], 'venv', 'bin', 'python')
                script_path = os.path.join(current_app.config['BASE_PATH'], 'run_sync.py')
                
                with open(LOG_PATH, "a") as log_file:
                    subprocess.Popen(
                        [python_executable, "-u", script_path, str(athlete_id)], # No activity_id here, just athlete_id for full sync
                        stdout=log_file,
                        stderr=log_file,
                        cwd=current_app.config['BASE_PATH']
                    )
            except Exception as e:
                print(f"[{datetime.now()}] ERROR: Failed to start background sync subprocess: {e}")
        # ------------ NEW USER TIRGGER ACTIVITY LOAD -------------------


    except Exception as e:
        print(f"[{datetime.now()}] CRITICAL: Failed to save user {athlete_id} to DB: {e}")
        return "Internal Database Error", 500
    finally:
        conn.close()

    # Redirect to the main dashboard
    return redirect(url_for('main.index'))

@auth_bp.route('/logout')
def logout():
    """Clears the session."""
    session.clear()
    return redirect(url_for('main.index'))


@auth_bp.route('/disconnect')
@login_required
def disconnect():
    """
    User-initiated deauthorization.
    Revokes Strava access, deletes local data, and logs out.
    """
    athlete_id = session.get('athlete_id')
    
    from core.database import get_db_connection, delete_db_user_data
    from core.strava_api import get_valid_access_token, post_deauthorization

    conn = get_db_connection()
    try:
        # 1. Get token and tell Strava to revoke access
        tokens = get_valid_access_token(conn, athlete_id)
        if tokens:
            post_deauthorization(tokens['access_token'])
            #print("TEST WARNING: User deauthorized triggered")
        
        # 2. Wipe local database for this user
        delete_db_user_data(athlete_id)
        #print("TEST WARNING: User DB cleanup triggered")
        
        # 3. Clear session
        session.clear()
        
        with open(LOG_PATH, "a") as log_file:
            log_file.write(f"\n[{datetime.now()}] ⚠️ USER DISCONNECT: Athlete {athlete_id} initiated full purge.\n")

        print(f"[{datetime.now()}] AUTH_LOG: User {athlete_id} disconnected and purged.")
        
    except Exception as e:
        print(f"[{datetime.now()}] ERROR: Disconnect failed for {athlete_id}: {e}")
    finally:
        conn.close()

    return redirect(url_for('main.index'))