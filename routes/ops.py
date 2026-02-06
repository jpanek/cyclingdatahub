# routes/ops.py
import subprocess
import os
import json
from flask import (
    Blueprint, redirect, url_for, flash, request, 
    session, current_app, jsonify
    )
from config import LOG_PATH, BASE_PATH
from core.database import run_query
from routes.auth import login_required
from datetime import datetime

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
    if res and len(res) > 0:
        total_activity_count = res[0].get('total', 0)
        total_streams_count = res[0].get('streams', 0)
    else:
        total_activity_count = 0
        total_streams_count = 0
    
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

@ops_bp.route('/webhook', methods=['GET', 'POST'])
def strava_webhook():
    """
    Handles Strava Webhook: 
    GET for subscription validation, POST for activity events.
    """
    # --- 1. THE HANDSHAKE (GET) ---
    if request.method == 'GET':
        hub_mode = request.args.get('hub.mode')
        hub_token = request.args.get('hub.verify_token')
        hub_challenge = request.args.get('hub.challenge')

        if hub_mode == 'subscribe' and hub_token == current_app.config['STRAVA_WEBHOOK_VERIFY_TOKEN']:
            print(f"[{datetime.now()}] WEBHOOK: Handshake successful.")
            return jsonify({"hub.challenge": hub_challenge}), 200
        
        print(f"[{datetime.now()}] WEBHOOK: Handshake failed (Unauthorized).")
        return "Unauthorized", 403

    # --- 2. THE EVENT (POST) ---
    if request.method == 'POST':
        data = request.get_json()

        #Security: check the webhook subscription ID:
        subscription_id = current_app.config.get('STRAVA_WEBHOOK_SUBSCRIPTION_ID')
        if data.get('subscription_id') != subscription_id:
            print(f"[{datetime.now()}] WEBHOOK: Ignoring event from unknown subscription {data.get('subscription_id')}")
            return "EVENT_RECEIVED", 200 # Still return 200 so Strava doesn't retry

        # LOG the webhook to create a trail of all updates/deletes/deauths
        log_file_path = os.path.join(current_app.config['BASE_PATH'], 'logs', 'webhook_events.log')
        try:
            with open(log_file_path, 'a') as f:
                log_entry = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "payload": data
                }
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            print(f"Failed to log webhook event: {e}")
        
        # For event "activity" and aspect "create" process:
        if data.get('object_type') == 'activity' and data.get('aspect_type') in ['create', 'update']:
            athlete_id = data.get('owner_id')
            activity_id = data.get('object_id')
            aspect = data.get('aspect_type')
            
            print(f"[{datetime.now()}] WEBHOOK: Activity {aspect} {activity_id} for athlete {athlete_id}. Triggering sync.")

            # Trigger the same subprocess logic you already use in sync_activities
            try:
                python_executable = os.path.join(BASE_PATH, 'venv', 'bin', 'python')
                script_path = os.path.join(BASE_PATH, 'run_sync.py')
                
                with open(LOG_PATH, "a") as log_file:
                    log_file.write(f"\n[{datetime.now()}] WEBHOOK TRIGGER: Activity {aspect} {activity_id} detected for {athlete_id}\n")
                    subprocess.Popen(
                        [python_executable, "-u", script_path, str(athlete_id), str(activity_id)],
                        stdout=log_file,
                        stderr=log_file,
                        cwd=BASE_PATH
                    )
            except Exception as e:
                print(f"[{datetime.now()}] WEBHOOK ERROR: Failed to start subprocess: {e}")

        # Always return 200 OK to Strava immediately
        return "EVENT_RECEIVED", 200