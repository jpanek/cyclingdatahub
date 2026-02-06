from flask import Blueprint, render_template, jsonify, request, session
from core.database import run_query
from routes.auth import login_required
import json

map_bp = Blueprint('map', __name__)

@map_bp.route('/map')
@login_required
def map_page():
    return render_template('map.html')

@map_bp.route('/api/map-data')
@login_required
def map_data():
    months = request.args.get('range', type=int, default=12)
    athlete_id = session.get('athlete_id')
    activity_type = request.args.get('type', default='Ride')
    search_term = request.args.get('search', default='')
    
    query = """
        SELECT 
            strava_id, 
            name, 
            map_polyline, 
            type,
            TO_CHAR(start_date_local, 'DD-MM-YYYY') as activity_date
        FROM activities 
        WHERE athlete_id = %s 
        and type != 'VirtualRide'
        AND map_polyline IS NOT NULL
        and map_polyline != ''
    """
    params = [athlete_id]

    # Filter by Activity Type (unless 'All' is selected)
    if activity_type != 'All':
        query += " AND type = %s"
        params.append(activity_type)

    # Filter by Search Term
    if search_term:
        query += " AND name ILIKE %s"
        params.append(f"%{search_term}%")

    # Add the date interval filter if range is not "Full History" (0)
    if months > 0:
        query += " AND start_date_local >= CURRENT_DATE - INTERVAL '%s months'"
        params.append(months)

    query += " ORDER BY start_date_local DESC"
    activities = run_query(query, params)
        
    type_query = """
        SELECT type, COUNT(*) as activity_count
        FROM activities
        WHERE athlete_id = %s
        AND type != 'VirtualRide'
        AND map_polyline IS NOT NULL
        AND map_polyline != ''
        GROUP BY type
        ORDER BY activity_count DESC;
    """
    available_types = run_query(type_query, [athlete_id])


    # Debugging the payload size
    json_string = json.dumps(activities, default=str)
    print(f"--- Map Data Debug ---")
    print(f"Athlete: {athlete_id} | Range: {months} months")
    print(f"Activities: {len(activities)}")
    print(f"Payload Size: {len(json_string)/1024/1024:.2f} MB")
    print(f"----------------------")

    return jsonify({
        'activities': activities,
        'available_types': available_types
    })



"""
    print(f"--- Map Data Debug ---")
    print(f"Activities: {len(activities)}")
    print(f"Payload Size: {size_mb:.2f} MB")
    print(f"----------------------")
"""