# core/queries.py

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
  AND start_date_local >= %s::timestamp
ORDER BY start_date_local desc;
"""

# Gets activity types ordered by frequency
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
    s.time_series, s.watts_series, s.heartrate_series, s.cadence_series, s.velocity_series, s.latlng_series,
    an.peak_5s, an.peak_1m, an.peak_5m, an.peak_20m, 
    an.peak_5s_hr, an.peak_1m_hr, an.peak_5m_hr, an.peak_20m_hr,
    an.weighted_avg_power, an.ride_ftp, an.aerobic_decoupling,
    an.variability_index, an.efficiency_factor, an.intensity_score
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