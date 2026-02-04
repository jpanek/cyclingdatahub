# routes/auth.py
from flask import Blueprint, session, redirect, url_for, current_app, request
from config import USER_STRAVA_ATHLETE_ID
from functools import wraps
from urllib.parse import urlencode
import requests

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

    # Next step (which we will do once this redirect works): 
    # Exchange this 'code' for an access_token via a POST request
    return f"Success! Got code: {code}. Now we can exchange this for a token."

@auth_bp.route('/logout')
def logout():
    """Clears the session."""
    session.clear()
    return redirect(url_for('main.index'))