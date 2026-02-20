# routes/main.py
import os
import csv, io
import json
from flask import (
    Blueprint, render_template, request, Response, jsonify,
    session, current_app, flash, redirect, url_for
)
from datetime import datetime, timedelta
from config import LOG_PATH
from core.database import run_query
from core.analysis import get_best_power_curve, get_performance_summary
from routes.auth import login_required
from core.processor import format_activities_to_markdown
from core.queries import (
    SQL_GET_ACTIVITY_TYPES_BY_COUNT, 
    SQL_MONTHLY_ACTIVITY_METRICS,
    SQL_ACTIVITY_DETAILS,
    SQL_PREVIOUS_ACTIVITY_ID,
    SQL_NEXT_ACTIVITY_ID,
    SQL_DAILY_ACTIVITIES_HISTORY,
    SQL_RAW_DATA,
    SQL_GET_USER_SETTINGS
)

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    athlete_id = session.get('athlete_id')
    if not athlete_id:
            return render_template('login.html')
    
    res = run_query("SELECT COUNT(*) as count FROM activities WHERE athlete_id = %s", (athlete_id,))
    activity_count = res[0]['count'] if res else 0
    #activity_count = 0
    return render_template('index.html', syncing=(activity_count == 0))

@main_bp.route('/dashboard')
@login_required
def dashboard():

    athlete_id = session.get('athlete_id')

    chart_data = run_query(SQL_MONTHLY_ACTIVITY_METRICS, (athlete_id,))
    activity_types = run_query(SQL_GET_ACTIVITY_TYPES_BY_COUNT, (athlete_id,))

    return render_template('dashboard.html', 
                           chart_data=chart_data,
                           activity_types=activity_types
    )

@main_bp.route('/activity/', defaults={'strava_id': 17196834322})
@main_bp.route('/activity/<int:strava_id>')
@login_required
def activity_detail(strava_id):
    athlete_id = session.get('athlete_id')
    results = run_query(SQL_ACTIVITY_DETAILS, (strava_id,))
    activity = results[0] if results else None
    
    # 1. Fetch the current ride's date first
    current_ride = run_query("SELECT start_date_local FROM activities WHERE strava_id = %s", (strava_id,))
    
    if current_ride:
        curr_date = current_ride[0]['start_date_local']
        
        recent_sql = """
            (SELECT strava_id, substr(name,1,30) as name, type, start_date_local 
             FROM activities 
             WHERE athlete_id = %s AND start_date_local <= %s
             ORDER BY start_date_local DESC LIMIT 10)
            UNION
            (SELECT strava_id, substr(name,1,30) as name, type, start_date_local 
             FROM activities 
             WHERE athlete_id = %s AND start_date_local > %s
             ORDER BY start_date_local ASC LIMIT 10)
            ORDER BY start_date_local DESC
        """
        recent_activities = run_query(recent_sql, (athlete_id, curr_date, athlete_id, curr_date))
    else:
        recent_activities = []

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
    prev_res = run_query(SQL_PREVIOUS_ACTIVITY_ID, (athlete_id, strava_id))
    next_res = run_query(SQL_NEXT_ACTIVITY_ID, (athlete_id, strava_id))
    prev_id = prev_res[0]['strava_id'] if prev_res else None
    next_id = next_res[0]['strava_id'] if next_res else None

    #get the best power curve:
    best_curve = get_best_power_curve(athlete_id, months=12)

    fitness_sql = """
        SELECT ctl, atl, tsb 
        FROM athlete_daily_metrics 
        WHERE athlete_id = %s AND date = %s::date
    """
    fitness_res = run_query(fitness_sql, (athlete_id, activity['start_date_local']))
    fitness_data = fitness_res[0] if fitness_res else None
        
    return render_template(
        'activity_detail.html', 
        activity=activity, 
        prev_id=prev_id, 
        next_id=next_id,
        best_power=best_curve,
        recent_activities=recent_activities,
        fitness=fitness_data
    )

@main_bp.route('/performance')
@login_required
def performance_dashboard():
    athlete_id = session.get('athlete_id')
    
    # Get 'months' from URL, default to 12
    months = request.args.get('months', default=12, type=int)
    
    # Update your get_performance_summary to accept the months parameter
    data = get_performance_summary(athlete_id, months_limit=months)

    return render_template(
        'performance.html',
        progression_json=json.dumps(data['progression']),
        yearly_bests=data['yearly_bests'],
        all_time_peaks=data['all_time_peaks'],
        current_filter=months # Pass it back to keep the dropdown synced
    )

@main_bp.route('/activities')
@login_required
def activities_list():
    athlete_id = session.get('athlete_id')
    activity_type = request.args.get('type') or None
    date_from = request.args.get('from') or (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    date_to = request.args.get('to') or datetime.now().strftime('%Y-%m-%d')
    export_format = request.args.get('export')

    # Fetch activities with filters
    activities = run_query(SQL_DAILY_ACTIVITIES_HISTORY, (
        athlete_id, 
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
    activity_types = run_query(SQL_GET_ACTIVITY_TYPES_BY_COUNT, (athlete_id,))
    
    return render_template(
        'activities.html', 
        activities=activities, 
        since_date=date_from,
        until_date=date_to,
        current_type=activity_type,
        activity_types=activity_types
    )

@main_bp.route('/log')
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

@main_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    athlete_id = session.get('athlete_id')
    
    # Handle the Reset/Clear action
    if request.args.get('clear') == 'true':
        from core.database import update_user_manual_settings
        update_user_manual_settings(athlete_id, clear_manual=True)
        flash("Manual overrides cleared. Reverting to system detection.", "info")
        return redirect(url_for('main.settings'))

    if request.method == 'POST':
        # 1. Process the data
        ftp = request.form.get('manual_ftp') or None
        max_hr = request.form.get('manual_max_hr') or None
        weight = request.form.get('weight') or None
        
        from core.database import update_user_manual_settings
        update_user_manual_settings(athlete_id, ftp=ftp, max_hr=max_hr, weight=weight)
        
        # 2. Flash the message
        flash("Settings updated successfully!", "success")
        
        # 3. REDIRECT back to the same page. 
        return redirect(url_for('main.settings'))

    results = run_query(SQL_GET_USER_SETTINGS, (athlete_id,))
    if not results:
        flash("User not found.", "danger")
        return redirect(url_for('main.index'))
        
    user = results[0]
    return render_template('settings.html', user=user)

@main_bp.route('/fitness')
@login_required
def fitness_dashboard():
    athlete_id = session.get('athlete_id')
    days = request.args.get('days', default=90, type=int)
    
    # Use ::float to prevent Decimal issues
    sql = """
        SELECT 
            to_char(date, 'YYYY-MM-DD') as d,
            round(tss::numeric, 1)::float as tss,
            round(ctl::numeric, 1)::float as ctl,
            round(atl::numeric, 1)::float as atl,
            round(tsb::numeric, 1)::float as tsb
        FROM athlete_daily_metrics
        WHERE athlete_id = %s
        ORDER BY date DESC
        LIMIT %s
    """
    rows = run_query(sql, (athlete_id, days))
    rows.reverse() 

    return render_template(
        'fitness.html',
        fitness_json=json.dumps(rows), # Ensure this variable matches the template
        current_days=days
    )

@main_bp.route('/privacy')
def privacy():
    return render_template('privacy.html')

@main_bp.route('/dump')
@login_required
def dump():
    athlete_id = session.get('athlete_id')
    days = request.args.get('days', default=7, type=int)    
    rows = run_query(SQL_RAW_DATA, (athlete_id, f'{days} days'))
    
    if not rows:
        return render_template('dump.html', markdown_data="No data found.", days=days)
    
    markdown_data = format_activities_to_markdown(rows)
    
    return render_template('dump.html', markdown_data=markdown_data, days=days)


@main_bp.route('/dump-raw')
@login_required
def dump_raw():
    days = request.args.get('days', default=7, type=int)
    athlete_id = session.get('athlete_id')
    rows = run_query(SQL_RAW_DATA, (athlete_id, f'{days} days'))
    
    if not rows:
        return Response("No data found.", mimetype='text/plain')

    markdown_data = format_activities_to_markdown(rows)
    
    # Return raw text directly to the browser
    return Response(markdown_data, mimetype='text/plain')

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