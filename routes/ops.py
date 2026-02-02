# routes/ops.py
import subprocess
import os
from flask import Blueprint, redirect, url_for, flash, request
from config import MY_ATHLETE_ID, LOG_PATH, BASE_PATH
from core.database import run_query
from core.queries import SQL_GET_USER_NAME

ops_bp = Blueprint('ops', __name__)

@ops_bp.app_context_processor
def inject_globals():
    """
    Injects global variables into all templates.
    """
    # Get User Name
    user_data = run_query(SQL_GET_USER_NAME, (MY_ATHLETE_ID,))
    name = user_data[0]['firstname'] if user_data else "Athlete"
    
    # Get Last Activity ID
    from core.queries import SQL_GET_LATEST_ACTIVITY_ID
    last_act_data = run_query(SQL_GET_LATEST_ACTIVITY_ID, (MY_ATHLETE_ID,))
    last_id = last_act_data[0]['strava_id'] if last_act_data else None
    
    return dict(
        current_user_name=name,
        current_athlete_id=MY_ATHLETE_ID,
        #current_athlete_id=None,
        last_activity_id=last_id
    )

@ops_bp.route('/sync-activities')
def sync_activities():
    """Triggers the background sync process."""
    try:
        python_executable = os.path.join(BASE_PATH, 'venv', 'bin', 'python')
        script_path = os.path.join(BASE_PATH, 'run_sync.py')
        
        with open(LOG_PATH, "a") as log_file:
            subprocess.Popen(
                [python_executable, "-u", script_path, str(MY_ATHLETE_ID)],
                stdout=log_file,
                stderr=log_file,
                cwd=BASE_PATH
            )
        flash("Sync process started successfully.", "info")
    except Exception as e:
        flash(f"Process failed to start: {str(e)}", "danger")
    
    return redirect(request.referrer or url_for('main.index'))