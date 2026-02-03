# routes/auth.py
from flask import Blueprint, session, redirect, url_for
from config import USER_STRAVA_ATHLETE_ID
from functools import wraps

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

@auth_bp.route('/logout')
def logout():
    """Clears the session."""
    session.clear()
    return redirect(url_for('main.index'))