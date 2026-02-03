--
-- PostgreSQL database dump
--

-- Dumped from database version 14.18 (Homebrew)
-- Dumped by pg_dump version 14.18 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: activities; Type: TABLE; Schema: public; Owner: jurajpanek
--

CREATE TABLE public.activities (
    strava_id bigint NOT NULL,
    athlete_id bigint,
    name text,
    type text,
    start_date_local timestamp without time zone,
    distance double precision,
    moving_time integer,
    elapsed_time integer,
    total_elevation_gain double precision,
    average_speed double precision,
    max_speed double precision,
    average_watts double precision,
    max_watts double precision,
    weighted_average_watts double precision,
    kilojoules double precision,
    average_heartrate double precision,
    max_heartrate double precision,
    average_cadence double precision,
    suffer_score integer,
    achievement_count integer,
    kudos_count integer,
    map_polyline text,
    device_name text,
    raw_json jsonb,
    updated_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.activities OWNER TO jurajpanek;

--
-- Name: COLUMN activities.distance; Type: COMMENT; Schema: public; Owner: jurajpanek
--

COMMENT ON COLUMN public.activities.distance IS 'Distance in meters';


--
-- Name: COLUMN activities.weighted_average_watts; Type: COMMENT; Schema: public; Owner: jurajpanek
--

COMMENT ON COLUMN public.activities.weighted_average_watts IS 'Calculated Normalized Power (NP)';


--
-- Name: activity_analytics; Type: TABLE; Schema: public; Owner: jurajpanek
--

CREATE TABLE public.activity_analytics (
    strava_id bigint NOT NULL,
    peak_5s integer,
    peak_1m integer,
    peak_5m integer,
    peak_20m integer,
    weighted_avg_power integer,
    ride_ftp integer,
    variability_index double precision,
    efficiency_factor double precision,
    intensity_score double precision,
    max_vam integer,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    aerobic_decoupling double precision,
    peak_5s_hr integer,
    peak_1m_hr integer,
    peak_5m_hr integer,
    peak_20m_hr integer,
    power_curve jsonb
);


ALTER TABLE public.activity_analytics OWNER TO jurajpanek;

--
-- Name: activity_streams; Type: TABLE; Schema: public; Owner: jurajpanek
--

CREATE TABLE public.activity_streams (
    id integer NOT NULL,
    strava_id bigint,
    time_series integer[],
    distance_series double precision[],
    velocity_series double precision[],
    heartrate_series integer[],
    cadence_series integer[],
    watts_series integer[],
    temp_series integer[],
    moving_series boolean[],
    latlng_series jsonb,
    updated_at timestamp without time zone DEFAULT now(),
    altitude_series double precision[]
);


ALTER TABLE public.activity_streams OWNER TO jurajpanek;

--
-- Name: activity_streams_id_seq; Type: SEQUENCE; Schema: public; Owner: jurajpanek
--

CREATE SEQUENCE public.activity_streams_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.activity_streams_id_seq OWNER TO jurajpanek;

--
-- Name: activity_streams_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: jurajpanek
--

ALTER SEQUENCE public.activity_streams_id_seq OWNED BY public.activity_streams.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: jurajpanek
--

CREATE TABLE public.users (
    athlete_id bigint NOT NULL,
    firstname text,
    lastname text,
    refresh_token text,
    access_token text,
    expires_at timestamp without time zone,
    updated_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.users OWNER TO jurajpanek;

--
-- Name: COLUMN users.refresh_token; Type: COMMENT; Schema: public; Owner: jurajpanek
--

COMMENT ON COLUMN public.users.refresh_token IS 'Permanent token used to generate new access tokens';


--
-- Name: activity_streams id; Type: DEFAULT; Schema: public; Owner: jurajpanek
--

ALTER TABLE ONLY public.activity_streams ALTER COLUMN id SET DEFAULT nextval('public.activity_streams_id_seq'::regclass);


--
-- Name: activities activities_pkey; Type: CONSTRAINT; Schema: public; Owner: jurajpanek
--

ALTER TABLE ONLY public.activities
    ADD CONSTRAINT activities_pkey PRIMARY KEY (strava_id);


--
-- Name: activity_analytics activity_analytics_pkey; Type: CONSTRAINT; Schema: public; Owner: jurajpanek
--

ALTER TABLE ONLY public.activity_analytics
    ADD CONSTRAINT activity_analytics_pkey PRIMARY KEY (strava_id);


--
-- Name: activity_streams activity_streams_pkey; Type: CONSTRAINT; Schema: public; Owner: jurajpanek
--

ALTER TABLE ONLY public.activity_streams
    ADD CONSTRAINT activity_streams_pkey PRIMARY KEY (id);


--
-- Name: activity_streams activity_streams_strava_id_key; Type: CONSTRAINT; Schema: public; Owner: jurajpanek
--

ALTER TABLE ONLY public.activity_streams
    ADD CONSTRAINT activity_streams_strava_id_key UNIQUE (strava_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: jurajpanek
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (athlete_id);


--
-- Name: idx_activity_streams_strava_id; Type: INDEX; Schema: public; Owner: jurajpanek
--

CREATE INDEX idx_activity_streams_strava_id ON public.activity_streams USING btree (strava_id);


--
-- Name: activities activities_athlete_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: jurajpanek
--

ALTER TABLE ONLY public.activities
    ADD CONSTRAINT activities_athlete_id_fkey FOREIGN KEY (athlete_id) REFERENCES public.users(athlete_id);


--
-- Name: activity_analytics activity_analytics_strava_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: jurajpanek
--

ALTER TABLE ONLY public.activity_analytics
    ADD CONSTRAINT activity_analytics_strava_id_fkey FOREIGN KEY (strava_id) REFERENCES public.activities(strava_id) ON DELETE CASCADE;


--
-- Name: activity_streams activity_streams_strava_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: jurajpanek
--

ALTER TABLE ONLY public.activity_streams
    ADD CONSTRAINT activity_streams_strava_id_fkey FOREIGN KEY (strava_id) REFERENCES public.activities(strava_id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

