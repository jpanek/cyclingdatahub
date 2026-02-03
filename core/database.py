# core/database.py

import psycopg2
from psycopg2.extras import execute_batch, Json
from datetime import datetime
from psycopg2.extras import RealDictCursor
import pandas as pd

try:
    from config import DB_NAME, DB_USER, DB_HOST, DB_PORT, DB_PASS
except ImportError:
    from config import DB_NAME, DB_USER, DB_HOST, DB_PORT
    DB_PASS = None

import numpy as np
from psycopg2.extensions import register_adapter, AsIs

def adapt_numpy_float64(numpy_float64):
    return AsIs(numpy_float64)

def adapt_numpy_int64(numpy_int64):
    return AsIs(numpy_int64)

# Register the adapters
register_adapter(np.float64, adapt_numpy_float64)
register_adapter(np.int64, adapt_numpy_int64)
register_adapter(np.float32, adapt_numpy_float64)
register_adapter(np.int32, adapt_numpy_int64)

def get_db_connection():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT
    )

def run_query(query, params=None):
    """Generic executor that handles both SELECT (returns rows) and INSERT/UPDATE (commits)."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            
            # If the query returns data (like SELECT), fetch it
            if cur.description is not None:
                return cur.fetchall()
            
            # If it's a WRITE operation (INSERT/UPDATE), we must commit
            conn.commit()
            return None
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def run_query_pd(query, params=None):
    """Generic executor that recycles get_db_connection and returns a DataFrame."""
    conn = get_db_connection()
    try:
        return pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()

def get_db_user_tokens(conn, athlete_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT access_token, refresh_token, expires_at FROM users WHERE athlete_id = %s",
            (athlete_id,)
        )
        return cur.fetchone()

def save_db_user_tokens(conn, athlete_id, tokens):
    """Updates only the token-related fields for an existing user."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE users SET 
                access_token = %s, refresh_token = %s, expires_at = to_timestamp(%s), updated_at = NOW()
            WHERE athlete_id = %s
        """, (tokens['access_token'], tokens['refresh_token'], tokens['expires_at'], athlete_id))
    conn.commit()

def get_db_user(conn, athlete_id):
    """Returns user row if exists, else None."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # We fetch the name here to use for logging
        cur.execute("SELECT firstname, lastname FROM users WHERE athlete_id = %s", (athlete_id,))
        return cur.fetchone()

def get_db_latest_timestamp_for_athlete(conn, athlete_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT MAX(start_date_local) FROM activities WHERE athlete_id = %s", 
            (athlete_id,)
        )
        res = cur.fetchone()[0]
        return int(res.timestamp()) if res else 0

def save_db_user_profile(conn, athlete_data, tokens):
    # Convert to Python datetime object first
    # This works whether tokens['expires_at'] is a datetime or an int
    exp = tokens['expires_at']
    if isinstance(exp, (int, float)):
        expires_dt = datetime.fromtimestamp(exp)
    else:
        expires_dt = exp

    with conn.cursor() as cur:
        sql = """
            INSERT INTO users (athlete_id, firstname, lastname, refresh_token, access_token, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s) -- Removed to_timestamp
            ON CONFLICT (athlete_id) DO UPDATE SET
                firstname = EXCLUDED.firstname,
                lastname = EXCLUDED.lastname,
                refresh_token = EXCLUDED.refresh_token,
                access_token = EXCLUDED.access_token,
                expires_at = EXCLUDED.expires_at,
                updated_at = NOW();
        """
        cur.execute(sql, (
            athlete_data['id'], athlete_data.get('firstname'), athlete_data.get('lastname'),
            tokens['refresh_token'], tokens['access_token'], expires_dt # Passing the object
        ))
    conn.commit()

def save_db_activities(conn, athlete_id, activities):
    insert_sql = """
        INSERT INTO activities (
            strava_id, athlete_id, name, type, start_date_local,
            distance, moving_time, elapsed_time, total_elevation_gain,
            average_speed, max_speed, average_watts, max_watts,
            weighted_average_watts, kilojoules, average_heartrate,
            max_heartrate, average_cadence, suffer_score,
            achievement_count, kudos_count, map_polyline, device_name, raw_json
        ) VALUES (
            %(id)s, %(athlete_id)s, %(name)s, %(type)s, %(start_date)s,
            %(dist)s, %(mov_t)s, %(ela_t)s, %(elev)s,
            %(avg_s)s, %(max_s)s, %(avg_w)s, %(max_w)s,
            %(weighted_w)s, %(kj)s, %(avg_hr)s,
            %(max_hr)s, %(avg_cad)s, %(suffer)s,
            %(achieve)s, %(kudos)s, %(poly)s, %(device)s, %(raw)s
        ) 
        ON CONFLICT (strava_id) DO UPDATE SET
            name = EXCLUDED.name, distance = EXCLUDED.distance,
            moving_time = EXCLUDED.moving_time, average_watts = EXCLUDED.average_watts,
            weighted_average_watts = EXCLUDED.weighted_average_watts,
            updated_at = NOW();
    """
    data = []
    for a in activities:
        data.append({
            'id': a['id'], 'athlete_id': athlete_id, 'name': a.get('name'),
            'type': a.get('type'), 'start_date': a.get('start_date_local'),
            'dist': a.get('distance'), 'mov_t': a.get('moving_time'),
            'ela_t': a.get('elapsed_time'), 'elev': a.get('total_elevation_gain'),
            'avg_s': a.get('average_speed'), 'max_s': a.get('max_speed'),
            'avg_w': a.get('average_watts'), 'max_w': a.get('max_watts'),
            'weighted_w': a.get('weighted_average_watts'), 'kj': a.get('kilojoules'),
            'avg_hr': a.get('average_heartrate'), 'max_hr': a.get('max_heartrate'),
            'avg_cad': a.get('average_cadence'), 'suffer': a.get('suffer_score'),
            'achieve': a.get('achievement_count'), 'kudos': a.get('kudos_count'),
            'poly': a.get('map', {}).get('summary_polyline'),
            'device': a.get('device_name'), 'raw': Json(a)
        })
    with conn.cursor() as cur:
        execute_batch(cur, insert_sql, data)
    conn.commit()

def save_db_activity_stream(conn, activity_id, streams_dict):
    """
    Inserts stream data into activity_streams table.
    Uses native Postgres arrays for series and Jsonb for latlng.
    """
    from psycopg2.extras import Json
    
    def get_stream_data(type_key):
        if type_key in streams_dict and 'data' in streams_dict[type_key]:
            return streams_dict[type_key]['data']
        return None

    sql = """
        INSERT INTO activity_streams (
            strava_id, time_series, distance_series, velocity_series, 
            heartrate_series, cadence_series, watts_series, 
            temp_series, moving_series, latlng_series, altitude_series, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT(strava_id) DO UPDATE SET
            time_series=EXCLUDED.time_series,
            distance_series=EXCLUDED.distance_series,
            velocity_series=EXCLUDED.velocity_series,
            heartrate_series=EXCLUDED.heartrate_series,
            cadence_series=EXCLUDED.cadence_series,
            watts_series=EXCLUDED.watts_series,
            temp_series=EXCLUDED.temp_series,
            moving_series=EXCLUDED.moving_series,
            latlng_series=EXCLUDED.latlng_series,
            altitude_series=EXCLUDED.altitude_series,
            updated_at=NOW();
    """
    
    latlng_raw = get_stream_data('latlng')
    latlng_value = Json(latlng_raw) if latlng_raw else None



    params = (
        activity_id,
        get_stream_data('time'),
        get_stream_data('distance'),
        get_stream_data('velocity_smooth'),
        get_stream_data('heartrate'),
        get_stream_data('cadence'),
        get_stream_data('watts'),
        get_stream_data('temp'),
        get_stream_data('moving'),
        latlng_value,
        get_stream_data('altitude') # This is the 11th param
    )

    with conn.cursor() as cur:
        cur.execute(sql, params)
    conn.commit()