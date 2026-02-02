# core/analysis.py

import numpy as np

def calculate_weighted_power(watts_series):
    """Calculates xPower / Normalized Power equivalent."""
    if not watts_series or len(watts_series) < 30:
        return 0
    series = np.array(watts_series)
    rolling_avg = np.convolve(series, np.ones(30)/30, mode='valid')
    weighted_pw = np.mean(rolling_avg ** 4) ** 0.25
    return int(weighted_pw)

def get_interval_bests(activity_data):
    """
    Returns peak power and the corresponding average HR during those specific power windows.
    """
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