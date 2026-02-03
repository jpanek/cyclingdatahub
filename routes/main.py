# routes/main.py
import os
import csv, io
import json
from flask import Blueprint, render_template, request, Response, jsonify
from datetime import datetime, timedelta
from config import MY_ATHLETE_ID, LOG_PATH
from core.database import run_query
from core.analysis import get_best_power_curve, get_performance_summary
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
    
    export_format = request.args.get('export')
    if export_format == 'json':
        return jsonify(activity)
    elif export_format == 'csv':
        return export_to_csv([activity]) # Reusing the list-based exporter

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

    print(activity.keys())

    #get the best power curve:
    best_curve = get_best_power_curve(MY_ATHLETE_ID, months=12)
        
    return render_template(
        'activity_detail.html', 
        activity=activity, 
        prev_id=prev_id, 
        next_id=next_id,
        best_power=best_curve
    )

@main_bp.route('/performance')
def performance_dashboard():
    """
    Renders the high-level performance metrics, including 
    power progression and yearly bests.
    """
    # get_performance_summary returns the dict with 'progression' and 'yearly_bests'
    data = get_performance_summary(MY_ATHLETE_ID)

    return render_template(
        'performance.html',
        progression_json=json.dumps(data['progression']),
        yearly_bests=data['yearly_bests'],
        all_time_peaks=data['all_time_peaks']
    )

@main_bp.route('/activities')
def activities_list():
    activity_type = request.args.get('type') or None
    date_from = request.args.get('from') or (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    date_to = request.args.get('to') or datetime.now().strftime('%Y-%m-%d')
    export_format = request.args.get('export')

    # Fetch activities with filters
    activities = run_query(SQL_DAILY_ACTIVITIES_HISTORY, (
        MY_ATHLETE_ID, 
        activity_type, activity_type, 
        date_from, 
        f"{date_to} 23:59:59"
    ))

    # Handle Export logic before rendering anything else
    if export_format == 'csv':
        return export_to_csv(activities)
    elif export_format == 'json':
        # Use a string conversion for datetime objects in JSON
        return jsonify(activities)

    # Use your existing query for the dropdown, ordered by count
    activity_types = run_query(SQL_GET_ACTIVITY_TYPES_BY_COUNT, (MY_ATHLETE_ID,))
    
    return render_template(
        'activities.html', 
        activities=activities, 
        since_date=date_from,
        until_date=date_to,
        current_type=activity_type,
        activity_types=activity_types
    )

def export_to_csv(data):
    if not data:
        return "No data to export", 400
    
    output = io.StringIO()
    # Use keys from first row for header
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)
    
    filename = f"activities_{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )