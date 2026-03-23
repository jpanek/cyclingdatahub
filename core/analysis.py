# core/analysis.py

import numpy as np
from core.database import run_query
from datetime import datetime, timedelta
import config

def get_zone_descriptions(active_ftp, active_max_hr):
    """
    Calculates absolute min/max values for Power and HR zones.
    Now pulls definitions from the database instead of config.py.
    """
    active_ftp = active_ftp or config.DEFAULT_FTP
    active_max_hr = active_max_hr or config.DEFAULT_MAX_HR
    
    # 1. Fetch all percentage-based zones from the DB
    sql = """
        SELECT category, zone_name, min_val, max_val 
        FROM training_zones 
        WHERE is_percentage = TRUE 
        ORDER BY category, zone_no
    """
    db_zones = run_query(sql)
    
    # 2. Reconstruct the dictionary format your template expects
    output = {'power': [], 'hr': []}
    
    for z in db_zones:
        # Determine if we multiply by FTP or Max HR
        basis = active_ftp if z['category'] == 'power' else active_max_hr
        
        z_data = {
            "name": z['zone_name'],
            "min": int(basis * float(z['min_val'])),
            "max": int(basis * float(z['max_val']))
        }
        
        if z['category'] in output:
            output[z['category']].append(z_data)
            
    return output

def sync_daily_fitness(athlete_id, start_date):
    """
    Re-computes CTL/ATL/TSB from start_date forward to today.
    Fills in gaps for days with 0 TSS.
    """
    # 1. Get the 'Seed' values from the day before the change
    seed_sql = """
        SELECT ctl, atl FROM athlete_daily_metrics 
        WHERE athlete_id = %s AND date < %s 
        ORDER BY date DESC LIMIT 1
    """
    seed = run_query(seed_sql, (athlete_id, start_date))
    
    current_ctl = seed[0]['ctl'] if seed else 0.0
    current_atl = seed[0]['atl'] if seed else 0.0
    
    # 2. Fetch all known TSS from rides and a generated calendar of days
    # This ensures we have a row for every single day, even rest days.
    calendar_sql = """
        WITH calendar AS (
            SELECT generate_series(%s::date, NOW()::date, '1 day')::date AS day
        )
        SELECT 
            c.day,
            COALESCE(SUM(aa.training_stress_score), 0) as daily_tss
        FROM calendar c
        LEFT JOIN activities a ON a.start_date_local::date = c.day AND a.athlete_id = %s
        LEFT JOIN activity_analytics aa ON a.strava_id = aa.strava_id
        GROUP BY c.day
        ORDER BY c.day
    """
    daily_tss_data = run_query(calendar_sql, (start_date, athlete_id))

    # 3. Process the chain
    results = []
    for row in daily_tss_data:
        tss = float(row['daily_tss'])
        
        # Exponentially Weighted Moving Average Formulas
        # CTL (42 day) | ATL (7 day)
        current_ctl = current_ctl + (tss - current_ctl) * (1 - np.exp(-1/42))
        current_atl = current_atl + (tss - current_atl) * (1 - np.exp(-1/7))
        current_tsb = current_ctl - current_atl
        
        results.append((
            athlete_id, row['day'], tss, 
            round(current_ctl, 2), round(current_atl, 2), round(current_tsb, 2)
        ))

    # 4. Batch Save
    save_sql = """
        INSERT INTO athlete_daily_metrics (athlete_id, date, tss, ctl, atl, tsb)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (athlete_id, date) DO UPDATE SET
            tss = EXCLUDED.tss, ctl = EXCLUDED.ctl, 
            atl = EXCLUDED.atl, tsb = EXCLUDED.tsb
    """
    for record in results:
        run_query(save_sql, record)
        
    return len(results)

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
    Returns independent peak power and peak heart rate for specific windows.
    """
    if intervals is None:
        intervals = {'5s': 5, '1m': 60, '5m': 300, '20m': 1200}

    watts = np.array(activity_data.get('watts_series') or [])
    hr = np.array(activity_data.get('heartrate_series') or [])
    cadence = np.array(activity_data.get('cadence_series') or [])
    
    results = {}
    for label, seconds in intervals.items():
        # 1. Calculate Peak Power independently
        if watts.size >= seconds:
            rolling_pwr = np.convolve(watts, np.ones(seconds)/seconds, mode='valid')
            results[f'peak_power_{label}'] = int(round(np.max(rolling_pwr)))
        else:
            results[f'peak_power_{label}'] = None
            
        # 2. Calculate Peak HR independently
        if hr.size >= seconds:
            rolling_hr = np.convolve(hr, np.ones(seconds)/seconds, mode='valid')
            results[f'peak_hr_{label}'] = int(round(np.max(rolling_hr)))
        else:
            results[f'peak_hr_{label}'] = None

        # 3. Calculate Peak Cadence independently
        if cadence.size >= seconds:
            rolling_cadence = np.convolve(cadence, np.ones(seconds)/seconds, mode='valid')
            results[f'peak_cadence_{label}'] = int(round(np.max(rolling_cadence)))
        else:
            results[f'peak_cadence_{label}'] = None
            
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
    
    intervals = {
        '5s': '5', 
        '1m': '60', 
        '5m': '300', 
        '10m': '600', 
        '20m': '1200', 
        '60m': '3600'
    }
    all_progression, all_time_peaks, recent_peaks = {}, {}, {}
    
    today = datetime.now().date()
    # Radar chart looks at last 30 days of actual data
    global_recent_cutoff = today - timedelta(days=30)
    
    for label, json_key in intervals.items():
        query = SQL_POWER_PROGRESSION
        # Pass the json_key into the query placeholders
        raw_data = run_query(query, (
            json_key,       # For SELECT
            athlete_id, 
            json_key,       # For IS NOT NULL check
            json_key,       # For > 0 check
            months_limit, 
            months_limit
        ))
        
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

def calculate_time_in_zones(series, baseline, category):
    """
    Calculates time spent in each zone by fetching definitions from the DB.
    category: 'power' or 'hr'
    """
    if not series or not baseline:
        return {}

    # Fetch zones for this category from the DB
    sql = """
        SELECT zone_name, min_val, max_val 
        FROM training_zones 
        WHERE category = %s AND is_percentage = TRUE 
        ORDER BY zone_no
    """
    zones = run_query(sql, (category,))
    
    series = np.array(series)
    tiz = {}
    
    for z in zones:
        # Use the boundaries from the DB relative to the baseline
        lower = baseline * float(z['min_val'])
        upper = baseline * float(z['max_val'])
        
        # Standard "Lower inclusive, Upper exclusive" logic
        seconds = int(np.sum((series >= lower) & (series < upper)))
        tiz[z['zone_name']] = seconds
        
    return tiz

def classify_ride(metrics):
    """
    Categorizes a ride based on physiological impact (Power/Intensity/Variability).
    No longer uses destination-based logic (Commutes).
    """
    duration_sec = metrics.get('duration_sec', 0)
    duration_min = duration_sec / 60
    
    if duration_sec == 0:
        return "unclassified"

    # 1. Percentages and Context
    tiz = metrics.get('power_tiz', {})
    def get_p(zone):
        return (float(tiz.get(zone, 0) or 0) / duration_sec) * 100

    p_z1, p_z2 = get_p('Z1'), get_p('Z2')
    p_z34 = get_p('Z3') + get_p('Z4')
    p_high = get_p('Z5') + get_p('Z6') + get_p('Z7')
    
    dist_km = (metrics.get('distance_m', 0) / 1000.0)
    m_per_km = metrics.get('elevation_gain', 0) / dist_km if dist_km > 0 else 0
    
    if_val = metrics.get('if_score', 0)
    vi = metrics.get('vi_score', 1.0) 

    # 2. Hierarchical Classification (Training POV)
    
    # High Intensity / Work Capacity
    if p_high > 12 or (p_high > 8 and if_val > 0.80):
        return "intervals"

    # Active Recovery (Low metabolic cost, high Z1)
    if if_val < 0.58 and p_z1 > 40:
        return "recovery"

    # Sustainable Intensity (Threshold & SweetSpot)
    if if_val >= 0.82 and vi < 1.05:
        return "threshold_tt"
    
    if 0.75 <= if_val <= 0.88 and p_z34 > 35 and vi < 1.05:
        return "tempo_ss"

    # Aerobic Base (Z2 Dominance)
    if p_z2 > 40 and vi < 1.10:
        return "long_endurance" if duration_min > 180 else "steady_endurance"

    # Mechanical/Structural Load (Climbing or Surges)
    if vi >= 1.12 or m_per_km > 15:
        return "punchy_race" if if_val > 0.75 else "hilly_aerobic"
    
    # Catch-all for unstructured movement
    return "mixed_general"