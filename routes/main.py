# routes/main.py
import json
import subprocess, os
from datetime import datetime
import pandas as pd
from flask import Blueprint, render_template, redirect, url_for, flash, request
from config import MY_ATHLETE_ID, LOG_PATH, BASE_PATH
from core.database import run_query, run_query_pd
from core.queries import SQL_GET_ACTIVITY_TYPES_BY_COUNT, SQL_MONTHLY_ACTIVITY_METRICS

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    return render_template('index.html')

@main_bp.route('/dashboard')
def dashboard():
    """Lightweight JS-based dashboard."""
    df = run_query_pd(SQL_MONTHLY_ACTIVITY_METRICS, (MY_ATHLETE_ID,))
    activity_types = run_query(SQL_GET_ACTIVITY_TYPES_BY_COUNT, (MY_ATHLETE_ID,))
    
    if not df.empty:
        # 1. Convert month to string so JSON can handle it
        df['month'] = pd.to_datetime(df['month']).dt.strftime('%b %Y')
        # 2. Convert DataFrame to a list of dictionaries
        chart_data = df.to_dict(orient='records')
    else:
        chart_data = []

    # Pass the list directly; we will stringify it in the HTML
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