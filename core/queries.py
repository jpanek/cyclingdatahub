# core/queries.py

SQL_ATHLETE_COUNTS="""
SELECT 
    (SELECT COUNT(*) FROM activities WHERE athlete_id = %s) as total,
    (SELECT COUNT(*) FROM activity_streams s 
     JOIN activities a ON s.strava_id = a.strava_id 
     WHERE a.athlete_id = %s) as streams
"""

SQL_MONTHLY_ACTIVITY_METRICS = """
SELECT 
    TO_CHAR(DATE_TRUNC('month', start_date_local), 'Mon YYYY') as month_label,
    TO_CHAR(DATE_TRUNC('month', start_date_local), 'YYYY-MM') as month_id,
    type,
    count(*) as activities,
    SUM(moving_time) / 3600.0 AS duration_hours,
    SUM(distance) / 1000.0 AS distance_km,
    SUM(kilojoules) AS total_kj
FROM activities 
WHERE athlete_id = %s 
GROUP BY month_label, month_id, type
ORDER BY month_id ASC;
"""

SQL_DAILY_ACTIVITIES = """
SELECT 
	start_date_local,	
	TO_CHAR(start_date_local, 'DD') as day_of_month,
  strava_id,
  name,
    type,
    distance / 1000.0 as distance_km,
    moving_time / 3600.0 as duration_hours,
    kilojoules as total_kj,
    total_elevation_gain,
    average_speed*3.6 as average_speed,
    max_speed*3.6 as max_speed,
    average_watts,
    max_watts,
    weighted_average_watts,
    kilojoules,
    average_heartrate,
    max_heartrate,
    average_cadence,
    suffer_score
FROM activities 
WHERE athlete_id = %s 
  AND TO_CHAR(start_date_local, 'YYYY-MM') = %s
ORDER BY start_date_local ASC;
"""

SQL_DAILY_ACTIVITIES_HISTORY = """
SELECT 
a.start_date_local as start_datetime, 
a.strava_id,
a.name,
a.type,    
a.distance / 1000.0 as distance_km,
a.moving_time / 3600.0 as duration_hours,
a.elapsed_time / 3600 as elapsed_hours,
a.total_elevation_gain as elevation_gain,
a.average_speed * 3.6 as average_speed,
a.max_speed * 3.6 as max_speed,
a.average_watts,
a.max_watts,
a.kilojoules,
a.average_heartrate,
a.max_heartrate,
a.average_cadence,
a.suffer_score,
s.weighted_avg_power,
s.variability_index,
s.intensity_score,
s.aerobic_decoupling,
s.peak_5s, 
s.peak_1m, 
s.peak_5m, 
s.peak_20m,
s.training_stress_score as tss,
NOT EXISTS (
        SELECT 1 FROM activity_streams st 
        WHERE st.strava_id = a.strava_id 
        LIMIT 1
    ) as streams_missing
FROM activities a
LEFT JOIN activity_analytics s ON a.strava_id = s.strava_id
WHERE a.athlete_id = %s
  AND (%s IS NULL OR a.type = %s)
  AND (a.start_date_local >= %s)
  AND (a.start_date_local <= %s)
ORDER BY a.start_date_local desc
"""

SQL_GET_ACTIVITY_TYPES_BY_COUNT = """
SELECT type, COUNT(*) as activity_count 
FROM activities 
WHERE athlete_id = %s 
GROUP BY type 
ORDER BY activity_count DESC;
"""

SQL_GET_USER_NAME = """
SELECT firstname, lastname FROM users WHERE athlete_id = %s;
"""

SQL_GET_USER_SETTINGS = """
SELECT 
    athlete_id, firstname, lastname, 
    manual_ftp, detected_ftp, ftp_source_strava_id, ftp_detected_at,
    manual_max_hr, detected_max_hr, hr_source_strava_id, hr_detected_at,
    weight, updated_at,
    manual_ftp_updated_at, manual_max_hr_updated_at
FROM users 
WHERE athlete_id = %s
"""

SQL_GET_LATEST_ACTIVITY_ID = """
SELECT strava_id 
FROM activities 
WHERE athlete_id = %s 
ORDER BY start_date_local DESC 
LIMIT 1;
"""

SQL_ACTIVITY_DETAILS = """
SELECT 
    a.strava_id, a.name, a.type, a.start_date_local, 
    a.distance / 1000.0 as distance_km, 
    a.moving_time, a.total_elevation_gain, a.average_watts, a.average_heartrate,
    a.average_speed, a.max_speed, a.max_watts, a.max_heartrate,
    a.average_cadence, a.kilojoules,
    s.time_series, s.watts_series, s.heartrate_series, s.cadence_series, s.velocity_series, s.latlng_series,
    an.peak_5s, an.peak_1m, an.peak_5m, an.peak_20m, 
    an.peak_5s_hr, an.peak_1m_hr, an.peak_5m_hr, an.peak_20m_hr,
    an.weighted_avg_power, an.baseline_ftp, an.aerobic_decoupling,
    an.variability_index, an.efficiency_factor, an.intensity_score,
    an.training_stress_score,
    an.power_curve,
    a.map_polyline,
    s.altitude_series
FROM activities a
JOIN activity_streams s ON a.strava_id = s.strava_id
LEFT JOIN activity_analytics an ON a.strava_id = an.strava_id
WHERE a.strava_id = %s;
"""

SQL_PREVIOUS_ACTIVITY_ID = """
SELECT strava_id FROM activities 
WHERE athlete_id = %s 
AND start_date_local < (SELECT start_date_local FROM activities WHERE strava_id = %s)
ORDER BY start_date_local DESC 
LIMIT 1;
"""

SQL_NEXT_ACTIVITY_ID = """
SELECT strava_id FROM activities 
WHERE athlete_id = %s 
AND start_date_local > (SELECT start_date_local FROM activities WHERE strava_id = %s)
ORDER BY start_date_local ASC 
LIMIT 1;
"""

SQL_POWER_PROGRESSION = """
    SELECT 
        a.start_date_local as date, 
        a.name as activity_name, 
        a.strava_id,
        aa.{col} as power,
        aa.baseline_ftp
    FROM activities a
    JOIN activity_analytics aa ON a.strava_id = aa.strava_id
    WHERE a.athlete_id = %s
    AND aa.{col} IS NOT NULL 
    AND aa.{col} > 0
    AND a.type IN ('Ride','VirtualRide')
    AND (
        %s = 0 OR 
        a.start_date_local >= NOW() - make_interval(months => %s)
    )
    ORDER BY a.start_date_local ASC
"""

SQL_YEARLY_PEAKS = """
SELECT 
    EXTRACT(YEAR FROM a.start_date_local) as year,
    MAX(peak_5s) as p5s,
    MAX(peak_1m) as p1m,
    MAX(peak_5m) as p5m,
    MAX(peak_20m) as p20m
FROM activity_analytics an
JOIN activities a ON an.strava_id = a.strava_id
WHERE a.athlete_id = %s
GROUP BY year
ORDER BY year DESC;
"""

SQL_SEASONAL_CURVES = """
SELECT an.power_curve 
FROM activity_analytics an 
JOIN activities a ON an.strava_id = a.strava_id 
WHERE a.athlete_id = %s 
AND EXTRACT(YEAR FROM a.start_date_local) = %s
"""

SQL_CRAWLER_BACKLOG = """
  SELECT a.strava_id, a.type, a.start_date_local
  FROM activities a
  LEFT JOIN activity_streams s ON a.strava_id = s.strava_id
  WHERE a.athlete_id = %s 
    AND a.streams_missing = FALSE
    --AND a.type IN ('Ride', 'VirtualRide')
    AND a.start_date_local >= %s
    AND s.strava_id IS NULL
  ORDER BY a.start_date_local DESC
  LIMIT %s
"""

SQL_RECALC_QUEUE = """
    SELECT strava_id, type, start_date_local
    FROM activities 
    WHERE athlete_id = %s 
      AND needs_recalculation = TRUE
    ORDER BY start_date_local ASC
    LIMIT %s
"""

SQL_INVALIDATE_FORWARD = """
    UPDATE activities 
    SET needs_recalculation = TRUE 
    WHERE strava_id IN (
        SELECT strava_id FROM activities 
        WHERE athlete_id = %s AND start_date_local >= %s
    )
"""

SQL_RAW_DATA = """
SELECT 
    t.athlete_id,
    t.strava_id,
    t.start_date_local::date as date,
    t.name,
    t.type,
    t.distance / 1000.0 as "Distance_km",
    (t.moving_time / 60) as "Duration_min",
    t.kilojoules as "Work_kJ",
    t.max_watts as "Max_Watts",
    aa.weighted_avg_power as "NP_Watts",
    aa.variability_index as "VI",
    t.average_heartrate as "Avg_HR",
    ROUND(((t.average_heartrate / NULLIF(t.max_heartrate, 0)) * 100)::numeric, 1) as "HR_Percent_Max",
    aa.intensity_score as "IF",
    aa.training_stress_score as "TSS",
    aa.baseline_ftp as "Baseline_FTP",
    aa.aerobic_decoupling as "Decoupling_Pct",
    aa.efficiency_factor as "Efficiency_EF",
    aa.power_curve as "Power_Curve"
FROM activities t
LEFT JOIN activity_analytics aa ON aa.strava_id = t.strava_id 
WHERE t.athlete_id = %s
  AND t.start_date_local >= CURRENT_DATE - INTERVAL %s
ORDER BY t.start_date_local DESC
"""

SQL_GET_HOME_SUMMARY = """
WITH latest_fitness AS (
    SELECT ctl, atl, tsb, date
    FROM athlete_daily_metrics
    WHERE athlete_id = %s
    ORDER BY date DESC
    LIMIT 1
),
latest_activity AS (
    SELECT 
        a.strava_id, a.name, a.start_date_local, 
        aa.training_stress_score as tss,
        aa.weighted_avg_power as watts,
        a.distance
    FROM activities a
    LEFT JOIN activity_analytics aa ON a.strava_id = aa.strava_id
    WHERE a.athlete_id = %s
    ORDER BY a.start_date_local DESC
    LIMIT 1
),
monthly_stats AS (
    SELECT 
        SUM(distance) / 1000.0 as mtd_km,
        SUM(moving_time) / 60.0 as mtd_minutes,
        count(*) mtd_activities
    FROM activities 
    WHERE athlete_id = %s 
    AND date_trunc('month', start_date_local) = date_trunc('month', CURRENT_DATE)
)
SELECT 
    u.firstname,
    f.date,
    u.manual_ftp, u.detected_ftp, u.ftp_detected_at as ftp_date,
    COALESCE(f.ctl, 0) as ctl, 
    COALESCE(f.atl, 0) as atl, 
    COALESCE(f.tsb, 0) as tsb,
    la.strava_id as last_id,
    la.name as last_name,
    la.tss as last_tss,
    la.watts as last_watts,
    (la.distance / 1000.0) as last_km,
    COALESCE(m.mtd_km, 0) as mtd_km,
    COALESCE(m.mtd_minutes, 0) as mtd_minutes,
    COALESCE(m.mtd_activities, 0) as mtd_activities
FROM users u
LEFT JOIN latest_fitness f ON TRUE
LEFT JOIN latest_activity la ON TRUE
LEFT JOIN monthly_stats m ON TRUE
WHERE u.athlete_id = %s;
"""