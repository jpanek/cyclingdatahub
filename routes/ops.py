# routes/ops.py
import subprocess
import os
from flask import Blueprint, redirect, url_for, flash, request, session # added session
from config import LOG_PATH, BASE_PATH
from core.database import run_query

ops_bp = Blueprint('ops', __name__)

@ops_bp.app_context_processor
def inject_globals():
    """
    Injects global variables into all templates based on the logged-in user.
    """
    athlete_id = session.get('athlete_id')
    
    # If no one is logged in, return safe defaults
    if not athlete_id:
        return dict(
            current_user_name="Guest",
            current_athlete_id=None,
            last_activity_id=None
        )

    # 1. Get User Name for the specific logged-in athlete
    from core.queries import SQL_GET_USER_NAME
    user_data = run_query(SQL_GET_USER_NAME, (athlete_id,))
    name = user_data[0]['firstname'] if user_data else "Athlete"
    
    # 2. Get Last Activity ID for the specific logged-in athlete
    from core.queries import SQL_GET_LATEST_ACTIVITY_ID
    last_act_data = run_query(SQL_GET_LATEST_ACTIVITY_ID, (athlete_id,))
    last_id = last_act_data[0]['strava_id'] if last_act_data else None
    
    return dict(
        current_user_name=name,
        current_athlete_id=athlete_id,
        last_activity_id=last_id
    )

@ops_bp.route('/sync-activities')
def sync_activities():
    # Use session instead of hardcoded ID
    athlete_id = session.get('athlete_id')
    if not athlete_id:
        flash("You must be logged in to sync.", "danger")
        return redirect(url_for('main.index'))

    try:
        python_executable = os.path.join(BASE_PATH, 'venv', 'bin', 'python')
        script_path = os.path.join(BASE_PATH, 'run_sync.py')
        
        with open(LOG_PATH, "a") as log_file:
            subprocess.Popen(
                [python_executable, "-u", script_path, str(athlete_id)],
                stdout=log_file,
                stderr=log_file,
                cwd=BASE_PATH
            )
        flash("Sync process started successfully.", "info")
    except Exception as e:
        flash(f"Process failed to start: {str(e)}", "danger")
    
    return redirect(request.referrer or url_for('main.index'))