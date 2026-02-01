-- schema.sql

-- Users table to store athlete profiles and OAuth tokens
CREATE TABLE IF NOT EXISTS users (
    athlete_id BIGINT PRIMARY KEY,
    firstname TEXT,
    lastname TEXT,
    refresh_token TEXT,
    access_token TEXT,
    expires_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Activities table for high-level ride data
CREATE TABLE IF NOT EXISTS activities (
    strava_id BIGINT PRIMARY KEY,
    athlete_id BIGINT REFERENCES users(athlete_id),
    name TEXT,
    type TEXT,
    start_date_local TIMESTAMP,
    distance FLOAT,
    moving_time INTEGER,
    elapsed_time INTEGER,
    total_elevation_gain FLOAT,
    average_speed FLOAT,
    max_speed FLOAT,
    average_watts FLOAT,
    max_watts FLOAT,
    weighted_average_watts FLOAT8, -- Updated to FLOAT8 per your change
    kilojoules FLOAT,
    average_heartrate FLOAT,
    max_heartrate FLOAT,
    average_cadence FLOAT,
    suffer_score INTEGER,
    achievement_count INTEGER,
    kudos_count INTEGER,
    map_polyline TEXT,
    device_name TEXT,
    raw_json JSONB,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Streams table (prepared for later use)
CREATE TABLE IF NOT EXISTS activity_streams (
    id SERIAL PRIMARY KEY,
    strava_id BIGINT REFERENCES activities(strava_id),
    time_series INTEGER[],
    distance_series FLOAT[],
    velocity_series FLOAT[],
    heartrate_series INTEGER[],
    cadence_series INTEGER[],
    watts_series INTEGER[],
    temp_series INTEGER[],
    moving_series BOOLEAN[],
    latlng_series JSONB,
    updated_at TIMESTAMP DEFAULT NOW()
);