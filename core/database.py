# core/database.py

import psycopg2
from psycopg2.extras import execute_batch, Json
from datetime import datetime
from zoneinfo import ZoneInfo
from psycopg2.extras import RealDictCursor
import pandas as pd
from core.map_utils import process_activity_map

import config

DB_NAME = getattr(config, 'DB_NAME')
DB_USER = getattr(config, 'DB_USER')
DB_HOST = getattr(config, 'DB_HOST')
DB_PORT = getattr(config, 'DB_PORT')
DB_PASS = getattr(config, 'DB_PASS', None)
MAP_SUMMARY_TOLERANCE = getattr(config, 'MAP_SUMMARY_TOLERANCE', 0.001)

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

def delete_db_activity(strava_id):
    """
    Removes an activity and its associated streams from the database.
    Uses run_query to handle transactions and connection management.
    """
    try:
        # 1. Delete streams first (child table)
        run_query("DELETE FROM activity_streams WHERE strava_id = %s", (strava_id,))
        
        # 2. Delete the main activity (parent table)
        run_query("DELETE FROM activities WHERE strava_id = %s", (strava_id,))
        
        print(f"[{datetime.now()}] DB_LOG: Activity deleted: {strava_id}")
        return True
    except Exception as e:
        print(f"[{datetime.now()}] DB_LOG: Error deleting activity {strava_id}: {e}")
        return False

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

def get_db_all_athletes():
    conn = get_db_connection()
    data = run_query("select athlete_id, firstname from users order by 1")
    return data

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
    exp = tokens['expires_at']
    if isinstance(exp, (int, float)):
        expires_dt = datetime.fromtimestamp(exp)
    else:
        expires_dt = exp

    with conn.cursor() as cur:
        sql = """
            INSERT INTO users (athlete_id, firstname, lastname, refresh_token, access_token, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (athlete_id) DO UPDATE SET
                firstname = EXCLUDED.firstname,
                lastname = EXCLUDED.lastname,
                refresh_token = EXCLUDED.refresh_token,
                access_token = EXCLUDED.access_token,
                expires_at = EXCLUDED.expires_at,
                updated_at = NOW()
            RETURNING (xmax = 0) AS is_insert;
        """
        cur.execute(sql, (
            athlete_data['id'], athlete_data.get('firstname'), athlete_data.get('lastname'),
            tokens['refresh_token'], tokens['access_token'], expires_dt
        ))
        
        # This will be True if it was a new user, False if it was an update
        is_insert = cur.fetchone()[0]
        
        athlete_id = athlete_data['id']
        name = f"{athlete_data.get('firstname')} {athlete_data.get('lastname')}"
        
        if is_insert:
            print(f"[{datetime.now()}] DB_LOG: New user created: {name} ({athlete_id})")
        else:
            print(f"[{datetime.now()}] DB_LOG: Existing user updated: {name} ({athlete_id})")
            
    conn.commit()
    return is_insert

def save_db_activities(conn, athlete_id, activities):
    insert_sql = """
        INSERT INTO activities (
            strava_id, athlete_id, name, type, start_date_local,
            distance, moving_time, elapsed_time, total_elevation_gain,
            average_speed, max_speed, average_watts, max_watts,
            weighted_average_watts, kilojoules, average_heartrate,
            max_heartrate, average_cadence, suffer_score,
            achievement_count, kudos_count, map_polyline, device_name, raw_json,
            summary_polyline, min_lat, max_lat, min_lng, max_lng
        ) VALUES (
            %(id)s, %(athlete_id)s, %(name)s, %(type)s, %(start_date)s,
            %(dist)s, %(mov_t)s, %(ela_t)s, %(elev)s,
            %(avg_s)s, %(max_s)s, %(avg_w)s, %(max_w)s,
            %(weighted_w)s, %(kj)s, %(avg_hr)s,
            %(max_hr)s, %(avg_cad)s, %(suffer)s,
            %(achieve)s, %(kudos)s, %(poly)s, %(device)s, %(raw)s,
            %(sum_poly)s, %(mi_lat)s, %(ma_lat)s, %(mi_lng)s, %(ma_lng)s
        ) 
        ON CONFLICT (strava_id) DO UPDATE SET
            name = EXCLUDED.name, 
            distance = EXCLUDED.distance,
            moving_time = EXCLUDED.moving_time, 
            average_watts = EXCLUDED.average_watts,
            weighted_average_watts = EXCLUDED.weighted_average_watts,
            summary_polyline = EXCLUDED.summary_polyline,
            min_lat = EXCLUDED.min_lat, 
            max_lat = EXCLUDED.max_lat,
            min_lng = EXCLUDED.min_lng, 
            max_lng = EXCLUDED.max_lng,
            updated_at = NOW();
    """
    data = []
    for a in activities:
        # 1. Clean the original polyline ('' to None)
        raw_poly = a.get('map', {}).get('summary_polyline')
        raw_poly = raw_poly if raw_poly else None
        
        # 2. Calculate summary and bbox on the fly
        sum_p, mi_lat, ma_lat, mi_lng, ma_lng = (None, None, None, None, None)
        if raw_poly:
            sum_p, mi_lat, ma_lat, mi_lng, ma_lng = process_activity_map(
                raw_poly, 
                tolerance=MAP_SUMMARY_TOLERANCE
            )

        # ===========================================================================
        #workaround for stupid timezone of Jakarta for my virtual rides:
        # 1. Start with the provided local time
        final_start_date = a.get('start_date_local')
        
        # 2. Targeted fix for the "Jakarta Zwift" bug
        # Check athlete, activity type, and specifically the incorrect timezone
        is_me = (athlete_id == 12689416)
        is_virtual = (a.get('type') == 'VirtualRide')
        is_jakarta = (a.get('timezone') == "(GMT+07:00) Asia/Jakarta")

        if is_me and is_virtual and is_jakarta:
            utc_str = a.get('start_date')
            if utc_str:
                # Convert UTC to Prague time (DST aware)
                utc_dt = datetime.fromisoformat(utc_str.replace('Z', '+00:00'))
                prague_dt = utc_dt.astimezone(ZoneInfo("Europe/Prague"))
                
                # Update the date to your actual home time
                final_start_date = prague_dt.strftime('%Y-%m-%dT%H:%M:%S')
        # ===========================================================================

        data.append({
            'id': a['id'], 'athlete_id': athlete_id, 'name': a.get('name'),
            'type': a.get('type'), 
            #'start_date': a.get('start_date_local'),
            'start_date': final_start_date,
            'dist': a.get('distance'), 'mov_t': a.get('moving_time'),
            'ela_t': a.get('elapsed_time'), 'elev': a.get('total_elevation_gain'),
            'avg_s': a.get('average_speed'), 'max_s': a.get('max_speed'),
            'avg_w': a.get('average_watts'), 'max_w': a.get('max_watts'),
            'weighted_w': a.get('weighted_average_watts'), 'kj': a.get('kilojoules'),
            'avg_hr': a.get('average_heartrate'), 'max_hr': a.get('max_heartrate'),
            'avg_cad': a.get('average_cadence'), 'suffer': a.get('suffer_score'),
            'achieve': a.get('achievement_count'), 'kudos': a.get('kudos_count'),
            'poly': raw_poly, 
            'device': a.get('device_name'), 'raw': Json(a),
            # The extra "Pirate" payload
            'sum_poly': sum_p, 
            'mi_lat': mi_lat, 'ma_lat': ma_lat, 
            'mi_lng': mi_lng, 'ma_lng': ma_lng
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

def save_db_daily_tss(athlete_id, ride_date):
    """
    Standalone helper to ensure the daily ledger reflects the SUM of TSS 
    for all activities on a specific date.
    """
    sql_daily_tss = """
        INSERT INTO athlete_daily_metrics (athlete_id, date, tss)
        VALUES (%s, %s::date, (
            SELECT COALESCE(SUM(aa.training_stress_score), 0)
            FROM activities a
            JOIN activity_analytics aa ON a.strava_id = aa.strava_id
            WHERE a.athlete_id = %s 
              AND a.start_date_local::date = %s::date
        ))
        ON CONFLICT (athlete_id, date) DO UPDATE SET
            tss = EXCLUDED.tss;
    """
    # Note: We pass the date and athlete ID twice to satisfy the subquery and the insert
    run_query(sql_daily_tss, (athlete_id, ride_date, athlete_id, ride_date))

def update_user_manual_settings(athlete_id, ftp=None, max_hr=None, weight=None, clear_manual=False):
    """
    Updates or clears manual settings.
    If clear_manual is True, it sets manual overrides to NULL.
    """
    if clear_manual:
        query = """
            UPDATE users 
            SET manual_ftp = NULL, 
                manual_max_hr = NULL, 
                manual_ftp_updated_at = NULL,
                updated_at = NOW()
            WHERE athlete_id = %s
        """
        return run_query(query, (athlete_id,))
    
    # Otherwise, update as normal
    query = """
        UPDATE users 
        SET manual_ftp = COALESCE(%s, manual_ftp), 
            manual_max_hr = COALESCE(%s, manual_max_hr), 
            weight = COALESCE(%s, weight),
            manual_ftp_updated_at = CASE WHEN %s IS NOT NULL THEN NOW() ELSE manual_ftp_updated_at END,
            manual_max_hr_updated_at = CASE WHEN %s IS NOT NULL THEN NOW() ELSE manual_max_hr_updated_at END, -- Added this
            updated_at = NOW()
        WHERE athlete_id = %s
    """
    return run_query(query, (ftp, max_hr, weight, ftp, max_hr, athlete_id))

def delete_db_user_data(athlete_id):
    """
    Completely removes a user and all their data in a single transaction.
    Optimized for high performance on large datasets.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # 1. Bulk delete streams using a join-style syntax
            cur.execute("""
                DELETE FROM activity_streams s
                USING activities a
                WHERE s.strava_id = a.strava_id
                AND a.athlete_id = %s
            """, (athlete_id,))
            
            # 2. Bulk delete all activities for this athlete
            cur.execute("DELETE FROM activities WHERE athlete_id = %s", (athlete_id,))
            
            # 3. Delete the user profile
            cur.execute("DELETE FROM users WHERE athlete_id = %s", (athlete_id,))
            
            print(f"[{datetime.now()}] DB_LOG: User {athlete_id} and all data purged.")
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[{datetime.now()}] DB_LOG: Error purging user {athlete_id}: {e}")
        return False
    finally:
        conn.close()

def invalidate_analytics_from_date(athlete_id, start_date):
    """
    Flags all analytics records for an athlete as 'needs_recalculation' 
    if they occur on or after the given start_date.
    """
    from core.queries import SQL_INVALIDATE_FORWARD
    try:
        # start_date should be a string 'YYYY-MM-DD HH:MM:SS'
        run_query(SQL_INVALIDATE_FORWARD, (athlete_id, start_date))
    except Exception as e:
        print(f"  ⚠️ Failed to invalidate forward: {e}")

def db_mark_streams_missing(strava_id):
    """Marks an activity as having no streams to prevent crawler loops."""
    sql = "UPDATE activities SET streams_missing = TRUE WHERE strava_id = %s"
    run_query(sql, (strava_id,))