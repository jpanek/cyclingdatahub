# routes/ops.py
import subprocess
import os
from flask import Blueprint, redirect, url_for, flash, request, session, current_app, render_template
from config import LOG_PATH, BASE_PATH
from core.database import run_query
from routes.auth import login_required

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
    
    from core.queries import (
        SQL_GET_USER_NAME,
        SQL_GET_LATEST_ACTIVITY_ID,
        SQL_ATHLETE_COUNTS
    )

    # 1. Get User Name for the specific logged-in athlete
    user_data = run_query(SQL_GET_USER_NAME, (athlete_id,))
    name = user_data[0]['firstname'] if user_data else "Athlete"
    
    # 2. Get Last Activity ID for the specific logged-in athlete
    last_act_data = run_query(SQL_GET_LATEST_ACTIVITY_ID, (athlete_id,))
    last_id = last_act_data[0]['strava_id'] if last_act_data else None

    # 3. Get activity counts:
    res = run_query(SQL_ATHLETE_COUNTS,(athlete_id, athlete_id))
    total_activity_count = res[0]['total']
    total_streams_count = res[0]['streams']
    
    return dict(
        current_user_name=name,
        current_athlete_id=athlete_id,
        last_activity_id=last_id,
        total_activity_count=total_activity_count,
        total_streams_count=total_streams_count
    )

@ops_bp.route('/sync-activities')
@login_required # Added this for safety
def sync_activities():
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
    
    # Force redirect back to the logs page, specifically the sync log view
    return redirect(url_for('ops.show_logs', type='sync'))

@ops_bp.route('/log')
@login_required
def show_logs():
    # Define allowed logs for security
    log_map = {
        'sync': 'run_sync_log.log',
        'crawler': 'crawler_log.log'
    }
    
    log_type = request.args.get('type', 'sync')
    filename = log_map.get(log_type, 'run_sync_log.log')
    
    log_path = os.path.join(current_app.root_path, 'logs', filename)
    
    content = ""
    if os.path.exists(log_path):
        with open(log_path, 'r') as f:
            lines = f.readlines()
            # Take last 200 lines and reverse them so newest is at the top
            content = "".join(reversed(lines[-200:]))
    else:
        content = f"Log file {filename} not found."

    return render_template('logs.html', content=content, log_type=log_type)