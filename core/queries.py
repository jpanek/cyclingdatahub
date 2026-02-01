# core/queries.py

# Fetches monthly duration (hours) per activity type
SQL_MONTHLY_ACTIVITY_METRICS = """
SELECT 
    DATE_TRUNC('month', start_date_local) AS month,
    type,
    count(*) as activities,
    SUM(moving_time) / 3600.0 AS duration_hours,
    SUM(distance) / 1000.0 AS distance_km,
    SUM(kilojoules) AS total_kj
FROM activities 
WHERE athlete_id = %s 
GROUP BY month, type
ORDER BY month asc;
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