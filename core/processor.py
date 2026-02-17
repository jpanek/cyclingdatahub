# core/processor.py

from datetime import datetime, timedelta
from core.database import run_query
from core.analysis import (
    calculate_weighted_power, 
    get_interval_bests, 
    calculate_vam,
    calculate_aerobic_decoupling
)
import numpy as np
from psycopg2.extras import Json
import config

def format_activities_to_markdown(rows):
    """
    Helper to transform database rows into a Markdown table string.
    """
    if not rows:
        return "No data found."

    # 1. Dynamically get headers
    headers = list(rows[0].keys())
    
    header_row = "| " + " | ".join(headers) + " |"
    separator_row = "| " + " | ".join([":---"] * len(headers)) + " |"
    
    table_lines = [header_row, separator_row]
    
    # 2. Build rows
    for r in rows:
        row_values = []
        for h in headers:
            val = r[h]
            # Special formatting for specific columns
            if h == "Curve" and val:
                import json
                val = json.dumps(val) 
            elif h == "Decp" and val is not None:
                val = f"{val}%"
            elif val is None:
                val = "N/A"
            row_values.append(str(val))
        table_lines.append("| " + " | ".join(row_values) + " |")
    
    return "\n".join(table_lines)


def process_activity_metrics(strava_id, force=False):
    """
    Calculates high-res metrics (TSS, IF, EF) and manages adaptive fitness baselines.
    Uses a tiered priming strategy to handle new users and reverse-sync order.
    """
    if not force:
        exists = run_query("SELECT 1 FROM activity_analytics WHERE strava_id = %s", (strava_id,))
        if exists: return False

    # 1. Fetch User & Activity Context
    sql_init = """
        SELECT a.athlete_id, a.start_date_local, 
               u.manual_ftp, u.detected_ftp, u.ftp_detected_at,
               u.manual_max_hr, u.detected_max_hr, u.hr_detected_at
        FROM activities a 
        JOIN users u ON u.athlete_id = a.athlete_id 
        WHERE a.strava_id = %s
    """
    init_res = run_query(sql_init, (strava_id,))
    if not init_res: return False

    act = dict(init_res[0])
    athlete_id = act['athlete_id']
    ride_date = act['start_date_local']

    # 2. TIERED PRIMING (Ensures a baseline exists within the 90-day window)
    if act['detected_ftp'] is None:
        # Step A: High-res check (Existing analytics)
        prime_sql = """
            SELECT MAX(peak_20m) * 0.95 as ftp, MAX(peak_1m_hr) as hr
            FROM activity_analytics aa
            JOIN activities a ON a.strava_id = aa.strava_id
            WHERE a.athlete_id = %s 
            AND a.start_date_local >= (%s::date - make_interval(days => %s))
            AND a.start_date_local < %s::date
        """
        p_res = run_query(prime_sql, (athlete_id, ride_date, config.FTP_LOOKBACK_DAYS, ride_date))
        
        # Step B: Summary fallback (Strava metadata)
        if not p_res or not p_res[0]['ftp']:
            fallback_sql = """
                SELECT MAX(weighted_average_watts) as ftp, MAX(max_heartrate) as hr
                FROM activities
                WHERE athlete_id = %s
                AND start_date_local >= (%s::date - make_interval(days => %s))
                AND start_date_local < %s::date
                AND weighted_average_watts > 0
            """
            p_res = run_query(fallback_sql, (athlete_id, ride_date, config.FTP_LOOKBACK_DAYS, ride_date))

        if p_res and p_res[0]['ftp']:
            p = p_res[0]
            run_query("""
                UPDATE users SET detected_ftp = %s, ftp_detected_at = %s,
                                 detected_max_hr = %s, hr_detected_at = %s
                WHERE athlete_id = %s
            """, (int(p['ftp']), ride_date, p['hr'], ride_date, athlete_id))
            
            # Local update so the current ride uses these values immediately
            act['detected_ftp'], act['detected_max_hr'] = int(p['ftp']), p['hr']
            act['ftp_detected_at'], act['hr_detected_at'] = ride_date, ride_date

    # 3. Fetch Streams
    stream_data = run_query("SELECT * FROM activity_streams WHERE strava_id = %s", (strava_id,))
    if not stream_data: return False
    s = stream_data[0]
    activity_data = {'watts_series': s['watts_series'], 'heartrate_series': s['heartrate_series']}

    # 4. Core Calculations
    weighted_pwr = calculate_weighted_power(s['watts_series'])
    bests = get_interval_bests(activity_data)
    vam = calculate_vam(s['temp_series'], s['time_series'])
    decoupling = calculate_aerobic_decoupling(s['watts_series'], s['heartrate_series'])

    ride_ftp_est = int(bests.get('peak_power_20m') * 0.95) if bests.get('peak_power_20m') else 0
    ride_max_hr = max(s['heartrate_series']) if s['heartrate_series'] else 0
    stale_limit = datetime.now() - timedelta(days=config.FTP_LOOKBACK_DAYS)

    # 5. Adaptive Baseline & Decay Logic
    is_ftp_stale = act['detected_ftp'] is not None and act['ftp_detected_at'] < stale_limit
    is_new_ftp_peak = act['detected_ftp'] is not None and ride_ftp_est > act['detected_ftp']
    
    if act['detected_ftp'] is None or is_new_ftp_peak or is_ftp_stale:
        run_query("""
            UPDATE users SET detected_ftp = %s, ftp_source_strava_id = %s, ftp_detected_at = %s 
            WHERE athlete_id = %s
        """, (ride_ftp_est, strava_id, ride_date, athlete_id))
        active_ftp = act['manual_ftp'] or ride_ftp_est
    else:
        active_ftp = act['manual_ftp'] or act['detected_ftp'] or config.DEFAULT_FTP

    # Max HR Decay/Update
    is_hr_stale = act['detected_max_hr'] is not None and act['hr_detected_at'] < stale_limit
    is_new_hr_peak = act['detected_max_hr'] is not None and ride_max_hr > act['detected_max_hr']
    if act['detected_max_hr'] is None or is_new_hr_peak or is_hr_stale:
        run_query("UPDATE users SET detected_max_hr = %s, hr_detected_at = %s WHERE athlete_id = %s", 
                  (ride_max_hr, ride_date, athlete_id))

    # 6. Training Load Scores
    avg_pwr = np.mean(s['watts_series']) if s['watts_series'] else 0
    avg_hr = np.mean(s['heartrate_series']) if s['heartrate_series'] else 0
    
    vi = round(weighted_pwr / avg_pwr, 2) if avg_pwr > 0 else 1.0
    ef = round(weighted_pwr / avg_hr, 2) if avg_hr > 0 else 0
    if_score = round(weighted_pwr / active_ftp, 2) if active_ftp > 0 else 0
    duration_sec = s['time_series'][-1] if s['time_series'] else 0
    tss = round(((duration_sec * weighted_pwr * if_score) / (active_ftp * 3600)) * 100, 1) if active_ftp > 0 else 0

    # 7. Power Curve Construction
    curve_durations = {str(d): d for d in [1, 2, 5, 10, 30, 60, 120, 300, 600, 900, 1200, 1800, 3600]}
    detailed_curve = get_interval_bests(activity_data, intervals=curve_durations)
    power_curve_json = {k.replace('peak_power_', ''): v for k, v in detailed_curve.items() if 'peak_power_' in k and v is not None}

    # 8. Save Final Analytics
    sql_save = """
    INSERT INTO activity_analytics (
        strava_id, peak_5s, peak_1m, peak_5m, peak_20m, 
        peak_5s_hr, peak_1m_hr, peak_5m_hr, peak_20m_hr,
        weighted_avg_power, ride_ftp, max_vam, aerobic_decoupling,
        variability_index, efficiency_factor, intensity_score, 
        training_stress_score, power_curve, updated_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
    ON CONFLICT (strava_id) DO UPDATE SET
        weighted_avg_power = EXCLUDED.weighted_avg_power,
        ride_ftp = EXCLUDED.ride_ftp,
        intensity_score = EXCLUDED.intensity_score,
        training_stress_score = EXCLUDED.training_stress_score,
        power_curve = EXCLUDED.power_curve,
        updated_at = NOW();
    """
    
    run_query(sql_save, (
        strava_id, 
        bests.get('peak_power_5s'), bests.get('peak_power_1m'), 
        bests.get('peak_power_5m'), bests.get('peak_power_20m'),
        bests.get('peak_hr_5s'), bests.get('peak_hr_1m'), 
        bests.get('peak_hr_5m'), bests.get('peak_hr_20m'),
        weighted_pwr, active_ftp, vam, decoupling,
        vi, ef, if_score, tss, Json(power_curve_json)
    ))
    return True