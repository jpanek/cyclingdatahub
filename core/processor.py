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
    Uses a tiered strategy: Manual Override (Date-Aware) > Detected Peak > Default.
    """
    if not force:
        exists = run_query("SELECT 1 FROM activity_analytics WHERE strava_id = %s", (strava_id,))
        if exists: return False

    # 1. Fetch User & Activity Context (Including manual timestamp)
    sql_init = """
        SELECT a.athlete_id, a.start_date_local, 
               u.manual_ftp, u.detected_ftp, u.ftp_detected_at,
               u.manual_max_hr, u.detected_max_hr, u.hr_detected_at,
               u.manual_ftp_updated_at
        FROM activities a 
        JOIN users u ON u.athlete_id = a.athlete_id 
        WHERE a.strava_id = %s
    """
    init_res = run_query(sql_init, (strava_id,))
    if not init_res: return False

    act = dict(init_res[0])
    athlete_id = act['athlete_id']
    ride_date = act['start_date_local']

    # 2. TIERED PRIMING
    if act['detected_ftp'] is None:
        prime_sql = """
            SELECT MAX(peak_20m) * 0.95 as ftp, MAX(peak_1m_hr) as hr
            FROM activity_analytics aa
            JOIN activities a ON a.strava_id = aa.strava_id
            WHERE a.athlete_id = %s 
            AND a.start_date_local >= (%s::date - make_interval(days => %s))
            AND a.start_date_local < %s::date
        """
        p_res = run_query(prime_sql, (athlete_id, ride_date, config.FTP_LOOKBACK_DAYS, ride_date))
        
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
    stale_limit = datetime.now() - timedelta(days=config.FTP_LOOKBACK_DAYS)

# 5. Point-in-Time Baseline Logic
    #  ---------------------------------------------------------------------------------------------------
    # PRIO 0: Check for time-travel (Rewind context for historical ride processing)
    if act['ftp_detected_at'] and ride_date < act['ftp_detected_at']:
         hist_sql = """
            SELECT MAX(peak_20m) * 0.95 as hist_ftp, 
                   MAX(peak_1m_hr) as hist_hr, 
                   MAX(a.start_date_local) as hist_date
            FROM activity_analytics aa
            JOIN activities a ON a.strava_id = aa.strava_id
            WHERE a.athlete_id = %s 
            AND a.start_date_local >= (%s::date - make_interval(days => %s))
            AND a.start_date_local < %s::date
         """
         h_res = run_query(hist_sql, (athlete_id, ride_date, config.FTP_LOOKBACK_DAYS, ride_date))
         if h_res and h_res[0]['hist_ftp']:
             act['detected_ftp'] = int(h_res[0]['hist_ftp'])
             act['detected_max_hr'] = h_res[0]['hist_hr']
             act['ftp_detected_at'] = h_res[0]['hist_date']
             act['hr_detected_at'] = h_res[0]['hist_date']
         else:
             act['detected_ftp'] = config.DEFAULT_FTP
             # If no history found, set date to long ago to trigger PRIO 2 decay/prime
             act['ftp_detected_at'] = ride_date - timedelta(days=config.FTP_LOOKBACK_DAYS + 1)

    # ---------------------------------------------------------------------------------------------------
    # PRIO 1: Manual FTP exists and the ride is done after the setting
    if act['manual_ftp'] and act['manual_ftp_updated_at'] and ride_date >= act['manual_ftp_updated_at']:
        active_ftp = act['manual_ftp']
        active_hr = act['manual_max_hr'] or act['detected_max_hr'] or config.DEFAULT_MAX_HR

    # -----------------------------------------------------------------------------------------------
    # PRIO 2: No Manual FTP provided
    else:
        stale_limit = ride_date - timedelta(days=config.FTP_LOOKBACK_DAYS)
        is_ftp_stale = act['detected_ftp'] is not None and act['ftp_detected_at'] < stale_limit
        is_new_ftp_peak = act['detected_ftp'] is not None and ride_ftp_est > act['detected_ftp']
        
        is_hr_stale = act['detected_max_hr'] is not None and act['hr_detected_at'] < stale_limit
        current_max_hr = bests.get('peak_hr_1s') or 0
    
        # PRIO 2-A: Must update detection profile
        if act['detected_ftp'] is None or is_new_ftp_peak or is_ftp_stale or is_hr_stale:

            if (is_ftp_stale or is_hr_stale) and not is_new_ftp_peak:
                # GRACEFUL DECAY
                decay_sql = """
                    SELECT MAX(peak_20m) * 0.95 as next_ftp, MAX(peak_1m_hr) as next_hr
                    FROM activity_analytics aa
                    JOIN activities a ON a.strava_id = aa.strava_id
                    WHERE a.athlete_id = %s 
                    AND a.start_date_local >= %s
                    AND a.start_date_local <= %s
                """
                decay_res = run_query(decay_sql, (athlete_id, stale_limit, ride_date))
                
                if decay_res and decay_res[0]['next_ftp']:
                    active_ftp = max(int(decay_res[0]['next_ftp']), ride_ftp_est)
                    active_hr = max(int(decay_res[0]['next_hr']), current_max_hr)
                else:
                    active_ftp = ride_ftp_est or config.DEFAULT_FTP
                    active_hr = current_max_hr or act['detected_max_hr'] or config.DEFAULT_MAX_HR
            else:
                # NEW PEAK or INITIAL PRIME
                active_ftp = ride_ftp_est
                active_hr = max(current_max_hr, act['detected_max_hr'] or 0)

            # Update the User's detection profile
            run_query("""
                UPDATE users SET 
                    detected_ftp = %s, ftp_source_strava_id = %s, ftp_detected_at = %s,
                    detected_max_hr = %s, hr_source_strava_id = %s, hr_detected_at = %s
                WHERE athlete_id = %s
            """, (active_ftp, strava_id, ride_date, active_hr, strava_id, ride_date, athlete_id))

        # PRIO 3: Steady State
        else:
            active_ftp = act['detected_ftp'] or config.DEFAULT_FTP
            active_hr = act['detected_max_hr'] or config.DEFAULT_MAX_HR

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

    # 8. Save Final Analytics (Updated to baseline_ftp)
    sql_save = """
    INSERT INTO activity_analytics (
        strava_id, peak_5s, peak_1m, peak_5m, peak_20m, 
        peak_5s_hr, peak_1m_hr, peak_5m_hr, peak_20m_hr,
        weighted_avg_power, baseline_ftp, max_vam, aerobic_decoupling,
        variability_index, efficiency_factor, intensity_score, 
        training_stress_score, power_curve, updated_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
    ON CONFLICT (strava_id) DO UPDATE SET
        weighted_avg_power = EXCLUDED.weighted_avg_power,
        baseline_ftp = EXCLUDED.baseline_ftp,
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