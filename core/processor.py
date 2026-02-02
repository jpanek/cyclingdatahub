# core/processor.py

from core.database import run_query
from core.analysis import (
    calculate_weighted_power, 
    get_interval_bests, 
    calculate_vam,
    calculate_aerobic_decoupling
)
import numpy as np

def process_activity_metrics(strava_id, force=False):
    """
    Fetches streams, calculates all derived metrics including VI, EF, and IF.
    Ignores cadence peaks to focus on Power/HR correlation.
    """
    if not force:
        exists = run_query("SELECT 1 FROM activity_analytics WHERE strava_id = %s", (strava_id,))
        if exists: return False

    stream_data = run_query("SELECT * FROM activity_streams WHERE strava_id = %s", (strava_id,))
    if not stream_data: return False
    
    s = stream_data[0]
    
    # Prepare data (Cadence is still passed for general use, but ignored for peaks)
    activity_data = {
        'watts_series': s['watts_series'],
        'heartrate_series': s['heartrate_series']
    }

    # 1. Core Calculations
    weighted_pwr = calculate_weighted_power(s['watts_series'])
    # This now returns linked Power/HR peaks only
    bests = get_interval_bests(activity_data)
    vam = calculate_vam(s['temp_series'], s['time_series'])
    decoupling = calculate_aerobic_decoupling(s['watts_series'], s['heartrate_series'])
    
    # 2. Ride FTP
    peak_20m = bests.get('peak_power_20m')
    ride_ftp = int(peak_20m * 0.95) if peak_20m else None

    # 3. Advanced Scores
    avg_pwr = np.mean(s['watts_series']) if s['watts_series'] else 0
    avg_hr = np.mean(s['heartrate_series']) if s['heartrate_series'] else 0
    
    vi = round(weighted_pwr / avg_pwr, 2) if avg_pwr > 0 else 1.0
    ef = round(weighted_pwr / avg_hr, 2) if avg_hr > 0 else 0
    intensity_score = round(weighted_pwr / ride_ftp, 2) if ride_ftp and ride_ftp > 0 else 0

    # 4. Save to Database
    sql = """
    INSERT INTO activity_analytics (
        strava_id, 
        peak_5s, peak_1m, peak_5m, peak_20m, 
        peak_5s_hr, peak_1m_hr, peak_5m_hr, peak_20m_hr,
        weighted_avg_power, ride_ftp, max_vam, aerobic_decoupling,
        variability_index, efficiency_factor, intensity_score, updated_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
    ON CONFLICT (strava_id) DO UPDATE SET
        peak_5s = EXCLUDED.peak_5s,
        peak_1m = EXCLUDED.peak_1m,
        peak_5m = EXCLUDED.peak_5m,
        peak_20m = EXCLUDED.peak_20m,
        peak_5s_hr = EXCLUDED.peak_5s_hr,
        peak_1m_hr = EXCLUDED.peak_1m_hr,
        peak_5m_hr = EXCLUDED.peak_5m_hr,
        peak_20m_hr = EXCLUDED.peak_20m_hr,
        weighted_avg_power = EXCLUDED.weighted_avg_power,
        ride_ftp = EXCLUDED.ride_ftp,
        max_vam = EXCLUDED.max_vam,
        aerobic_decoupling = EXCLUDED.aerobic_decoupling,
        variability_index = EXCLUDED.variability_index,
        efficiency_factor = EXCLUDED.efficiency_factor,
        intensity_score = EXCLUDED.intensity_score,
        updated_at = NOW();
    """
    
    run_query(sql, (
        strava_id, 
        bests.get('peak_power_5s'), bests.get('peak_power_1m'), 
        bests.get('peak_power_5m'), bests.get('peak_power_20m'),
        bests.get('peak_hr_5s'), bests.get('peak_hr_1m'), 
        bests.get('peak_hr_5m'), bests.get('peak_hr_20m'),
        weighted_pwr, ride_ftp, vam, decoupling,
        vi, ef, intensity_score
    ))
    return True