# routes/main.py
import os
from flask import Blueprint, render_template
from datetime import datetime, timedelta
from config import MY_ATHLETE_ID, LOG_PATH
from core.database import run_query
from core.queries import (
    SQL_GET_ACTIVITY_TYPES_BY_COUNT, 
    SQL_MONTHLY_ACTIVITY_METRICS,
    SQL_ACTIVITY_DETAILS,
    SQL_PREVIOUS_ACTIVITY_ID,
    SQL_NEXT_ACTIVITY_ID,
    SQL_DAILY_ACTIVITIES_HISTORY
)

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    return render_template('index.html')

@main_bp.route('/dashboard')
def dashboard():
    chart_data = run_query(SQL_MONTHLY_ACTIVITY_METRICS, (MY_ATHLETE_ID,))
    activity_types = run_query(SQL_GET_ACTIVITY_TYPES_BY_COUNT, (MY_ATHLETE_ID,))

    return render_template('dashboard.html', 
                           chart_data=chart_data,
                           activity_types=activity_types
    )

@main_bp.route('/log')
def view_log():
    content = "No logs found."
    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, 'r') as f:
                lines = f.readlines()
                # Get last 100 lines and reverse so newest is on top
                content = "".join(reversed(lines[-100:]))
        except Exception as e:
            content = f"Error reading log: {str(e)}"
    
    return render_template('log_viewer.html', content=content)

@main_bp.route('/activity/', defaults={'strava_id': 17196834322})
@main_bp.route('/activity/<int:strava_id>')
def activity_detail(strava_id):
    results = run_query(SQL_ACTIVITY_DETAILS, (strava_id,))
    activity = results[0] if results else None
    
    if not activity:
        return "Activity details or streams not found.", 404
    
    # Map pre-calculated DB columns to the UI structure
    activity['interval_bests'] = {
        '5s':  {'power': activity.get('peak_5s'),  'hr': activity.get('peak_5s_hr')},
        '1m':  {'power': activity.get('peak_1m'),  'hr': activity.get('peak_1m_hr')},
        '5m':  {'power': activity.get('peak_5m'),  'hr': activity.get('peak_5m_hr')},
        '20m': {'power': activity.get('peak_20m'), 'hr': activity.get('peak_20m_hr')}
    }

    # Prev/Next logic stays the same
    prev_res = run_query(SQL_PREVIOUS_ACTIVITY_ID, (MY_ATHLETE_ID, strava_id))
    next_res = run_query(SQL_NEXT_ACTIVITY_ID, (MY_ATHLETE_ID, strava_id))
    prev_id = prev_res[0]['strava_id'] if prev_res else None
    next_id = next_res[0]['strava_id'] if next_res else None

    print(activity['interval_bests'])
        
    return render_template(
        'activity_detail.html', 
        activity=activity, 
        prev_id=prev_id, 
        next_id=next_id
    )

@main_bp.route('/activities')
def activities_list():
    # Calculate date 30 days ago
    since_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    print(since_date)
    
    # Run query with athlete_id and the date string
    activities = run_query(SQL_DAILY_ACTIVITIES_HISTORY, (MY_ATHLETE_ID, since_date))

    print(activities)
    
    return render_template(
        'activities.html', 
        activities=activities, 
        since_date=since_date
    )