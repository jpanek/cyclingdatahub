# routes/main.py
import os
import csv, io
import json
from flask import (
    Blueprint, render_template, request, Response, jsonify,
    session, current_app, flash, redirect, url_for, abort
)
from datetime import datetime, timedelta
from config import LOG_PATH
from core.database import run_query, get_db_zone_for_value, get_athlete_ftp
from core.analysis import get_best_power_curve, get_performance_summary, get_zone_descriptions
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
    SQL_GET_USER_SETTINGS,
    SQL_GET_HOME_SUMMARY,
    SQL_ADMIN_OVERVIEW, 
    SQL_ADMIN_CRAWLER_ACTIVITIES_BACKLOG, 
    SQL_ADMIN_CRAWLER_ANALYTICS_BACKLOG,
    SQL_DB_SIZE, SQL_TABLE_STATS
)

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    athlete_id = session.get('athlete_id')
    if not athlete_id:
            return render_template('login.html')
    
    res = run_query("SELECT COUNT(*) as count FROM activities WHERE athlete_id = %s", (athlete_id,))
    activity_count = res[0]['count'] if res else 0

    #summary for user:
    summary = run_query(SQL_GET_HOME_SUMMARY, (athlete_id, athlete_id, athlete_id, athlete_id))[0]

    #activity_count = 0
    return render_template('index.html',
            syncing=(activity_count == 0),
            summary=summary
    )

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

@main_bp.route('/activity/', defaults={'strava_id': None})
@main_bp.route('/activity/<int:strava_id>')
@login_required
def activity_detail(strava_id):
    athlete_id = session.get('athlete_id')

    # If no ID is provided, find the latest one dynamically
    if strava_id is None:
        from core.queries import SQL_GET_LATEST_ACTIVITY_ID
        last_act_data = run_query(SQL_GET_LATEST_ACTIVITY_ID, (athlete_id,))
        if last_act_data:
            strava_id = last_act_data[0]['strava_id']
        else:
            abort(404, description="No activities found for your profile.")
        
    results = run_query(SQL_ACTIVITY_DETAILS, (strava_id,))

    if not results:
        abort(404, description=f"Activity details for ID {strava_id} not found.")
    activity = results[0] if results else None

    #0. Get the laps:
    laps = []
    if activity['resource_state'] == 3:
        laps_sql = """
            SELECT * FROM activity_laps 
            WHERE strava_id = %s 
              AND is_hidden = FALSE
            ORDER BY start_index ASC
        """
        laps = run_query(laps_sql, (strava_id,))
    
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
        SELECT date, ctl, atl, tsb 
        FROM athlete_daily_metrics 
        WHERE athlete_id = %s 
          AND date <= %s::date
        ORDER BY date DESC
        LIMIT 2
    """
    fitness_res = run_query(fitness_sql, (athlete_id, activity['start_date_local']))
    
    fitness_data = fitness_res[0] if len(fitness_res) > 0 else {}
    yesterday_data = fitness_res[1] if len(fitness_res) > 1 else None

    current_tsb = fitness_data.get('tsb')
    tsb_zone = get_db_zone_for_value('tsb',current_tsb)

    # Calculate deltas
    deltas = {}
    if yesterday_data:
        for metric in ['ctl', 'atl', 'tsb']:
            if fitness_data.get(metric) is not None and yesterday_data.get(metric) is not None:
                deltas[metric] = fitness_data[metric] - yesterday_data[metric]

    zone_ranges = get_zone_descriptions(
        activity.get('baseline_ftp'), 
        activity.get('baseline_max_hr')
    )

    return render_template(
        'activity_detail.html', 
        activity=activity, 
        prev_id=prev_id, 
        next_id=next_id,
        best_power=best_curve,
        recent_activities=recent_activities,
        fitness=fitness_data,
        fitness_deltas=deltas,
        tsb_zone=tsb_zone,
        zone_ranges=zone_ranges,
        laps=laps
    )

@main_bp.route('/performance')
@login_required
def performance_dashboard():
    athlete_id = session.get('athlete_id')
    
    months = request.args.get('months', default=12, type=int)
    
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
    #print(activities)

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

# --------------------------------------------------------------------------------
@main_bp.route('/log')
@login_required
def show_logs():
    
    admin_id = current_app.config.get('USER_STRAVA_ATHLETE_ID')
    if session.get('athlete_id') != admin_id:
        abort(403)

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
            content = "".join(reversed(lines[-300:]))
    else:
        content = f"Log file {filename} not found."

    return render_template('logs.html', content=content, log_type=log_type)

# --------------------------------------------------------------------------------
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

    effective_ftp = user['manual_ftp'] or user['detected_ftp'] or 0
    effective_hr = user['manual_max_hr'] or user['detected_max_hr'] or 0

    zone_ranges = get_zone_descriptions(effective_ftp, effective_hr)

    return render_template('settings.html', 
                           user=user,
                           zone_ranges=zone_ranges
    )

# --------------------------------------------------------------------------------
@main_bp.route('/fitness')
@login_required
def fitness_dashboard():
    athlete_id = session.get('athlete_id')
    days = request.args.get('days', default=30, type=int)
    
    # 1. Fetch historical metrics including ACWR
    sql = """
        SELECT 
            to_char(date, 'YYYY-MM-DD') as d,
            round(tss::numeric, 1)::float as tss,
            round(ctl::numeric, 1)::float as ctl,
            round(atl::numeric, 1)::float as atl,
            round(tsb::numeric, 1)::float as tsb,
            CASE 
                WHEN ctl > 0 THEN round((atl / ctl)::numeric, 2)::float 
                ELSE 0 
            END as acwr
        FROM athlete_daily_metrics
        WHERE athlete_id = %s
        ORDER BY date DESC
        LIMIT %s
    """
    rows = run_query(sql, (athlete_id, days))
    rows.reverse() # Chronological order for the chart

    # 2. Fetch Training Zones (TSB and ACWR)
    tsb_zones = run_query("""
        SELECT zone_name, min_val, max_val, description, color_code 
        FROM training_zones 
        WHERE category = 'tsb' 
        ORDER BY min_val DESC
    """)
    
    acwr_zones = run_query("""
        SELECT zone_name, min_val, max_val, color_code 
        FROM training_zones 
        WHERE category = 'acwr'
    """)

    # 3. Calculate Insights for the "Pro" Tiles
    latest = rows[-1] if rows else None
    ramp_rate = 0
    days_to_fresh = 0
    acwr_color = "secondary"
    acwr_status = "Unknown"

    if latest:
        # 7-Day Fitness Ramp
        if len(rows) >= 8:
            ramp_rate = round(latest['ctl'] - rows[-8]['ctl'], 1)
        
        # Estimate days to recovery (TSB > 0)
        if latest['tsb'] < 0:
            days_to_fresh = max(1, round(abs(latest['tsb']) / 6))

        # Determine ACWR styling from DB zones
        for zone in acwr_zones:
            if zone['min_val'] <= latest['acwr'] <= zone['max_val']:
                acwr_color = zone['color_code']
                acwr_status = zone['zone_name']
                break
    
    #Time in zones:
    power_zones_meta = run_query("""
        SELECT zone_name, color_code, description, zone_no, min_val, max_val
        FROM training_zones 
        WHERE category = 'power' 
        ORDER BY zone_no ASC
    """)
    tiz_parts = ", ".join([f"SUM((power_tiz->>'{z['zone_name']}')::int) as {z['zone_name']}" for z in power_zones_meta])
    sql_tiz = f"""
        SELECT {tiz_parts}
        FROM activity_analytics aa
        JOIN activities a ON aa.strava_id = a.strava_id
        WHERE a.athlete_id = %s 
          AND a.start_date_local >= (CURRENT_DATE - INTERVAL '{days} days')
          AND a.device_watts = true
    """
    tiz_data = run_query(sql_tiz, (athlete_id,))[0]
    normalized_tiz = {k.lower(): v for k, v in tiz_data.items()}
    total_seconds = sum(filter(None, normalized_tiz.values())) or 1

    distribution_data = []

    ftp = get_athlete_ftp(athlete_id)

    for zone in power_zones_meta:
        # Use lowercase for the lookup key
        lookup_key = zone['zone_name'].lower() 
        seconds = normalized_tiz.get(lookup_key) or 0
        
        # Get min/max percentage from DB (e.g., 0.55, 0.75)
        z_min_pct = zone.get('min_val') or 0
        z_max_pct = zone.get('max_val') or 0
        
        # Calculate absolute watts
        watts_min = int(ftp * z_min_pct)
        watts_max = int(ftp * z_max_pct)

        distribution_data.append({
            "label": zone['zone_name'], # Keep 'Z1' for the UI
            "description": zone['description'],
            "color": zone['color_code'],
            "percent": round((seconds / total_seconds) * 100, 1),
            "hours": round(seconds / 3600, 1),
            "range": f"{watts_min}W - {watts_max}W"
        })

    # 4. Fetch Recent Activity Feed (Timeline Version)
    sql_recent = """
        SELECT 
            a.strava_id, a.name,
            to_char(a.start_date_local, 'DD/MM') as date_short,
            to_char(a.start_date_local, 'Dy') as day_name,
            COALESCE(cm.display_name, 'MIXED') as class_label,
            cm.accent_color,
            cm.bg_color,
            cm.icon_class,
            round(aa.intensity_score::numeric, 2) as if_score,
            round(aa.variability_index::numeric, 2) as vi,
            round(aa.training_stress_score::numeric, 0) as tss
        FROM activities a
        JOIN activity_analytics aa ON a.strava_id = aa.strava_id
        LEFT JOIN activity_classification_meta cm ON aa.classification = cm.slug
        WHERE a.athlete_id = %s 
        AND a.start_date_local >= (CURRENT_DATE - INTERVAL '%s days')
        ORDER BY a.start_date_local ASC
    """
    recent_activities = run_query(sql_recent, (athlete_id, days))

    return render_template(
        'fitness.html',
        fitness_json=json.dumps(rows),
        tsb_zones=tsb_zones,
        current_days=days,
        ramp_rate=ramp_rate,
        latest=latest,
        days_to_fresh=days_to_fresh,
        acwr_color=acwr_color,
        acwr_status=acwr_status,
        distribution_json=json.dumps(distribution_data),
        dist_data_list=distribution_data,
        recent_activities=recent_activities
    )

# --------------------------------------------------------------------------------
@main_bp.route('/laps-editor/<int:strava_id>')
def laps_editor(strava_id):
    # Fetch the specific activity data
    activity_results = run_query("SELECT * FROM activities WHERE strava_id = %s", (strava_id,))
    
    if not activity_results:
        return "Activity not found", 404
        
    activity = activity_results[0]

    # Fetch laps (all of them, including hidden/manual)
    laps = run_query("""
        SELECT * FROM activity_laps 
        WHERE strava_id = %s 
        ORDER BY start_index ASC, is_manual DESC
    """, (strava_id,))
    
    return render_template('edit_laps.html', 
                           strava_id=strava_id, 
                           activity=activity, 
                           laps=laps)

# --------------------------------------------------------------------------------
@main_bp.route('/admin')
@login_required
def admin_dashboard():
    # Security check: strictly restricted to your Strava ID
    admin_id = current_app.config.get('USER_STRAVA_ATHLETE_ID')
    if session.get('athlete_id') != admin_id:
        abort(403)

    # Pulling history window from app config instead of direct import
    history_days = current_app.config.get('CRAWL_HISTORY_DAYS', 500)

    # Fetching data
    overview = run_query(SQL_ADMIN_OVERVIEW)
    crawler = run_query(SQL_ADMIN_CRAWLER_ACTIVITIES_BACKLOG, (history_days,))
    analytics = run_query(SQL_ADMIN_CRAWLER_ANALYTICS_BACKLOG)
    
    db_size_res = run_query(SQL_DB_SIZE)
    db_size = db_size_res[0]['total_db_size'] if db_size_res else "N/A"
    table_stats = run_query(SQL_TABLE_STATS)
    
    return render_template('admin_overview.html', 
                           overview=overview, 
                           crawler=crawler, 
                           analytics=analytics,
                           history_days=history_days,
                           db_size=db_size,
                           table_stats=table_stats)

# --------------------------------------------------------------------------------
@main_bp.route('/privacy')
def privacy():
    return render_template('privacy.html')

# --------------------------------------------------------------------------------
@main_bp.route('/dump')
@login_required
def dump():
    athlete_id = session.get('athlete_id')
    days = request.args.get('days', default=7, type=int)    
    rows = run_query(SQL_RAW_DATA, (athlete_id, f'{days} days'))
    
    if not rows:
        return render_template('dump.html', markdown_data="No data found.", days=days)
    
    markdown_data = format_activities_to_markdown(rows)
    print(markdown_data)
    
    return render_template('dump.html', markdown_data=markdown_data, days=days)

# --------------------------------------------------------------------------------
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

# --------------------------------------------------------------------------------
@main_bp.route('/coach')
@login_required
def coach_page():
    # Instant load
    return render_template('coach.html')

@main_bp.route('/coach/load')
def coach_load():
    athlete_id = session.get('athlete_id')
    from core.coach import get_coaching_advice
    
    # This is the "Slow" AI call
    advice = get_coaching_advice(athlete_id)
    
    # Returns just the card HTML to be swapped in
    return render_template('coach_content.html', advice=advice)

# --------------------------------------------------------------------------------
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