# core/coach.py
from core.database import run_query
from core.queries import (
    SQL_GET_COACH_FITNESS_TREND, 
    SQL_GET_COACH_RECENT_ACTIVITY_DETAILS,
    SQL_GET_LATEST_ACTIVITY_ID
)
from core.processor import get_athlete_context
from static.ai_setting import DEBUG_OUTPUT, SYSTEM_INSTRUCTION
from decimal import Decimal
from datetime import date, datetime, timedelta
from google import genai
import config
import json

def _clean_row(row):
    """Converts DB-specific types (Decimal, Date) to standard Python types."""
    if not row:
        return {}
    clean = {}
    for k, v in dict(row).items():
        if isinstance(v, Decimal):
            clean[k] = float(v)
        elif isinstance(v, (date, datetime)):
            clean[k] = v.isoformat()
        else:
            clean[k] = v
    return clean

def _strip_zeros(data_dict):
    """Removes keys with 0, 0.0, or None to save tokens in the AI prompt."""
    if not isinstance(data_dict, dict):
        return data_dict
    return {k: v for k, v in data_dict.items() if v not in [0, 0.0, None, {}]}

def gather_coach_context(athlete_id, history_days=14, full_detail_limit=7):
    """
    Gathers a training brief with optimized integer rounding and metadata context.
    """
    # 1. Get Athlete Profile
    latest_act = run_query(SQL_GET_LATEST_ACTIVITY_ID, (athlete_id,))
    athlete_profile = {}
    
    if latest_act:
        strava_id = latest_act[0]['strava_id']
        raw_context = get_athlete_context(strava_id)
        if raw_context:
            athlete_profile = {
                "ftp": raw_context.get('manual_ftp') or raw_context.get('detected_ftp'),
                "max_hr": raw_context.get('manual_max_hr') or raw_context.get('detected_max_hr')
            }

    # 2. Get Fitness Trend
    raw_trend = run_query(SQL_GET_COACH_FITNESS_TREND, (athlete_id,))
    trend_data = [_clean_row(r) for r in raw_trend]
    
    ramp_rate_7d = 0
    tsb_min_period = 0
    if trend_data:
        tsb_min_period = min(r['tsb'] for r in trend_data[-history_days:])
        if len(trend_data) >= 7:
            # Keep 1 decimal for ramp rate as 3.1 vs 3.9 is a real difference
            ramp_rate_7d = round(trend_data[-1]['ctl'] - trend_data[-7]['ctl'], 1)

    # Only send 7 days of daily rows to save tokens
    short_trend = trend_data[-7:] if len(trend_data) > 7 else trend_data

    # 3. Get Recent Activities
    raw_activities = run_query(SQL_GET_COACH_RECENT_ACTIVITY_DETAILS, (athlete_id,))
    
    today = datetime.now().date()
    seven_days_ago = (today - timedelta(days=7)).isoformat()
    limit_date = (today - timedelta(days=history_days)).isoformat()
    
    activity_data = []
    this_week_tss = 0
    prev_week_tss = 0
    
    for i, r in enumerate(raw_activities):
        clean_r = _clean_row(r)
        act_date_str = clean_r.get('date')
        
        if act_date_str < limit_date:
            continue

        tss = clean_r.get('tss') or 0
        if act_date_str >= seven_days_ago:
            this_week_tss += tss
        else:
            prev_week_tss += tss

        # Activity Payload
        act_item = {
            "date": act_date_str,
            "name": clean_r.get('name'),
            "type": clean_r.get('type'),
            "tss": int(round(tss)),
            "intensity": clean_r.get('intensity'),
            "dur_min": clean_r.get('dur_min'),
        }

        # Add heavy metrics only for the most recent items
        if i < full_detail_limit:
            act_item.update({
                "decoupling_pct": clean_r.get('decoupling_pct'),
                "ef": clean_r.get('ef'),
                "vi": clean_r.get('vi'),
                "power_tiz": _strip_zeros(clean_r.get('power_tiz')),
                "hr_tiz": _strip_zeros(clean_r.get('hr_tiz'))
            })
        
        activity_data.append(act_item)

    # 4. Final Assembly
    return {
        "metadata": {
            "history_days_analyzed": history_days,
            "analysis_date": today.isoformat()
        },
        "athlete_profile": athlete_profile,
        "fitness_summary": {
            "current_ctl": int(round(trend_data[-1]['ctl'])) if trend_data else 0,
            "current_tsb": int(round(trend_data[-1]['tsb'])) if trend_data else 0,
            "tsb_min_in_period": int(round(tsb_min_period)),
            "ramp_rate_7d": ramp_rate_7d,
            "this_week_total_tss": int(round(this_week_tss)),
            "prev_week_total_tss": int(round(prev_week_tss)),
            "workload_delta_pct": int(round(((this_week_tss - prev_week_tss) / (prev_week_tss or 1)) * 100))
        },
        "fitness_trend_7d": short_trend,
        "recent_activities": activity_data
    }

def get_coaching_advice(athlete_id, goal="General Fitness", debug=False):
    
    if debug:
            print('Debug output only, not running fetch')
            latest_act_res = run_query(SQL_GET_LATEST_ACTIVITY_ID, (athlete_id,))
            mock_id = latest_act_res[0]['strava_id'] if latest_act_res else 0
            
            advice = DEBUG_OUTPUT.copy()
            advice['referenced_strava_id'] = mock_id
            return advice

    #1. Get latest activity of the athlete:
    latest_act_res = run_query(SQL_GET_LATEST_ACTIVITY_ID, (athlete_id,))
    if not latest_act_res:
            return {
                "referenced_strava_id": None,
                "status": ["No activities found."], 
                "insights": [], 
                "recommendation": {"target": "N/A", "alternative": "N/A"}
            }

    latest_strava_id = latest_act_res[0]['strava_id']

    today_date = datetime.now().date()

    #2. Check if there is already record in the DB:
    cached_res = run_query(
            """
            SELECT advice_json, goal, generated_at
            FROM coach_advice 
            WHERE athlete_id = %s 
            AND strava_id = %s 
            AND DATE(generated_at) = %s 
            ORDER BY generated_at DESC LIMIT 1
            """,
            (athlete_id, latest_strava_id, today_date)
        )
    if cached_res:
        advice = cached_res[0]['advice_json']
        saved_goal = cached_res[0].get('goal', 'General Fitness')
        

        advice_data = json.loads(advice) if isinstance(advice, str) else advice
        advice_data['referenced_strava_id'] = latest_strava_id
        advice_data['goal'] = saved_goal
        advice_data['generated_at'] = cached_res[0]['generated_at']
        return advice_data
    
    #3. No cached coaching advices, get them from AI:
    print('Coaching fetched form Google Gemini') #-------------------------------
    context = gather_coach_context(athlete_id)
    context['current_goal'] = goal

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    prompt = f"User Current Goal: {goal}\n\nAthlete Data Context: {json.dumps(context)}"

    try:
        response = client.models.generate_content(
            model=config.GEMINI_API_MODEL,
            # We tell the model to strictly return JSON
            config={
                'system_instruction': SYSTEM_INSTRUCTION,
                'response_mime_type': 'application/json'
            },
            contents=prompt
        )
        
        # Parse the JSON string back to dict
        advice_data = json.loads(response.text)

        # save it to db
        run_query(
            "INSERT INTO coach_advice (athlete_id, strava_id, advice_json, goal) VALUES (%s, %s, %s, %s)",
            (athlete_id, latest_strava_id, json.dumps(advice_data), goal)
        )
        advice_data['referenced_strava_id'] = latest_strava_id
        advice_data['goal'] = goal
        advice_data['generated_at'] = datetime.now()
        return advice_data

    except Exception as e:
        # Fallback structure so the UI doesn't break
        return {
            "referenced_strava_id": latest_strava_id,
            "status": "Coach is currently offline.",
            "insights": [str(e)],
            "recommendation": {
                "target": "No available", 
                "alternative": "Not available",
                "long_term_gap": "Analysis unavailable."
                },
            "metrics_flagged": []
        }