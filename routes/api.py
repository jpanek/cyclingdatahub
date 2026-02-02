# # routes/api.py
from flask import Blueprint, jsonify
from core.database import run_query
from core.queries import SQL_DAILY_ACTIVITIES
from config import MY_ATHLETE_ID # Assuming this is where your ID is stored

api_bp = Blueprint('api', __name__)

# Descriptive name: specifically for the monthly drill-down
@api_bp.route('/activities/by-month/<month_year>')
def get_monthly_activities(month_year):
    """Returns individual activities for a specific month (e.g., 'Feb 2026')"""
    print(month_year)
    data = run_query(SQL_DAILY_ACTIVITIES, (MY_ATHLETE_ID, month_year))
    return jsonify(data)

# Reserved for your future idea:
@api_bp.route('/activities/range')
def get_activities_range():
    # You would access this via /api/activities/range?start=2026-01-01&end=2026-01-31
    # start_date = request.args.get('start')
    # end_date = request.args.get('end')
    return jsonify({"message": "API not ready yet"}), 200