# core/analysis.py

import numpy as np
from core.database import run_query
from datetime import datetime, timedelta

def calculate_weighted_power(watts_series):
    """Calculates xPower / Normalized Power equivalent."""
    if not watts_series or len(watts_series) < 30:
        return 0
    series = np.array(watts_series)
    rolling_avg = np.convolve(series, np.ones(30)/30, mode='valid')
    weighted_pw = np.mean(rolling_avg ** 4) ** 0.25
    return int(weighted_pw)

def get_interval_bests(activity_data, intervals=None):
    """
    Returns peak power and the corresponding average HR during those specific power windows.
    """
    if intervals is None:
        intervals = {'5s': 5, '1m': 60, '5m': 300, '20m': 1200}

    watts = np.array(activity_data.get('watts_series') or [])
    hr = np.array(activity_data.get('heartrate_series') or [])
    
    results = {}
    for label, seconds in intervals.items():
        if watts.size >= seconds:
            # 1. Find the peak power window
            rolling_pwr = np.convolve(watts, np.ones(seconds)/seconds, mode='valid')
            max_idx = np.argmax(rolling_pwr)
            
            results[f'peak_power_{label}'] = int(round(rolling_pwr[max_idx]))
            
            # 2. Get average HR for the EXACT same time window
            if hr.size >= watts.size:
                hr_window = hr[max_idx : max_idx + seconds]
                results[f'peak_hr_{label}'] = int(round(np.mean(hr_window))) if hr_window.size > 0 else None
            else:
                results[f'peak_hr_{label}'] = None
        else:
            results[f'peak_power_{label}'] = None
            results[f'peak_hr_{label}'] = None
            
    return results

def calculate_vam(temp_series, time_series):
    """
    Calculates Max VAM (Vertical Meters per Hour) over a 5-min window.
    Requires altitude/temp_series and time_series.
    """
    if not temp_series or len(temp_series) < 300:
        return 0
    
    elev = np.array(temp_series)
    # Get elevation gain over 5 minute windows (300 seconds)
    v_gain = elev[300:] - elev[:-300]
    # Convert to hourly rate: (gain / 5 mins) * 12
    vam_series = v_gain * 12
    return int(np.max(vam_series)) if len(vam_series) > 0 else 0

def calculate_aerobic_decoupling(watts_series, hr_series):
    """
    Compares Efficiency Factor of 1st half vs 2nd half.
    Values > 5% suggest lack of aerobic endurance or fatigue.
    """
    if not watts_series or not hr_series or len(watts_series) < 600:
        return None
    
    mid = len(watts_series) // 2
    
    def get_ef(w, hr):
        avg_w = np.mean(w)
        avg_hr = np.mean(hr)
        return avg_w / avg_hr if avg_hr > 0 else 0

    ef1 = get_ef(watts_series[:mid], hr_series[:mid])
    ef2 = get_ef(watts_series[mid:], hr_series[mid:])
    
    if ef1 == 0: return 0
    decoupling = ((ef1 - ef2) / ef1) * 100
    return round(decoupling, 2)

def get_best_power_curve(athlete_id, months=12):
    """
    Computes the 'Best' envelope based on a rolling number of months history.
    Default is 12 months.
    """
    # Calculate the date 'X' months ago
    # Using roughly 30 days per month for the SQL filter
    since_date = (datetime.now() - timedelta(days=months * 30)).strftime('%Y-%m-%d')

    sql = """
        SELECT an.power_curve 
        FROM activity_analytics an 
        JOIN activities a ON an.strava_id = a.strava_id 
        WHERE a.athlete_id = %s 
        AND a.start_date_local >= %s
    """
    results = run_query(sql, (athlete_id, since_date))
    
    if not results:
        return {}

    overall_best = {}
    for row in results:
        curve = row.get('power_curve') or {}
        for duration_str, power in curve.items():
            d = int(duration_str)
            if power is not None:
                if d not in overall_best or power > overall_best[d]:
                    overall_best[d] = power
                
    return overall_best

def get_performance_summary(athlete_id, months_limit=12):
    from core.queries import SQL_POWER_PROGRESSION, SQL_YEARLY_PEAKS
    from core.database import run_query
    from datetime import datetime, timedelta
    
    intervals = {'5s': 'peak_5s', '1m': 'peak_1m', '5m': 'peak_5m', '20m': 'peak_20m'}
    all_progression, all_time_peaks, recent_peaks = {}, {}, {}
    
    today = datetime.now().date()
    # Radar chart looks at last 30 days of actual data
    global_recent_cutoff = today - timedelta(days=30)
    
    for label, col in intervals.items():
        query = SQL_POWER_PROGRESSION.replace("{col}", col)
        # PASS TWICE: Once for the '0' check, once for the interval
        raw_data = run_query(query, (athlete_id, months_limit, months_limit))
        
        if not raw_data:
            all_progression[label], all_time_peaks[label], recent_peaks[label] = [], 0, 0
            continue

        # Convert dates once
        for r in raw_data:
            if hasattr(r['date'], 'date'): r['date'] = r['date'].date()
        
        raw_data.sort(key=lambda x: x['date'])
        
        current_max = 0
        processed = []
        
        for i, row in enumerate(raw_data):
            pwr = row['power'] or 0
            ride_date = row['date']
            
            if pwr > current_max: current_max = pwr
            
            # Efficient Seasonal Max: Look back in the already sorted raw_data
            window_start = ride_date - timedelta(days=30)
            seasonal_max = 0
            # Only iterate backwards until we leave the 30-day window
            for j in range(i, -1, -1):
                if raw_data[j]['date'] < window_start: break
                val = raw_data[j]['power'] or 0
                if val > seasonal_max: seasonal_max = val

            processed.append({
                'x': ride_date.isoformat(),
                'y': pwr,
                'seasonal_record': seasonal_max,
                'ftp': row.get('baseline_ftp') or 0,
                'name': row['activity_name'],
                'id': str(row['strava_id'])
            })
            
        all_progression[label] = processed
        all_time_peaks[label] = current_max
        recent_peaks[label] = max([r['power'] for r in raw_data if r['date'] >= global_recent_cutoff] or [0])

    yearly_bests = run_query(SQL_YEARLY_PEAKS, (athlete_id,))
    return {
        'progression': all_progression,
        'yearly_bests': yearly_bests,
        'all_time_peaks': all_time_peaks,
        'recent_peaks': recent_peaks
    }