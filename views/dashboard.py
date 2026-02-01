import sys
import os
import streamlit as st
import pandas as pd

# Path fix for local modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.database import run_query_pd
from core.queries import (
    SQL_MONTHLY_ACTIVITY_METRICS, SQL_GET_ACTIVITY_TYPES_BY_COUNT,
    SQL_GET_USER_NAME
)
from config import MY_ATHLETE_ID

st.set_page_config(page_title="Activity Dashboard", layout="wide")

# --- 1. Data Fetching ---
user_df = run_query_pd(SQL_GET_USER_NAME, params=(MY_ATHLETE_ID,))
athlete_name = f"{user_df.iloc[0]['firstname']} {user_df.iloc[0]['lastname']}" if not user_df.empty else "Athlete"

types_count_df = run_query_pd(SQL_GET_ACTIVITY_TYPES_BY_COUNT, params=(MY_ATHLETE_ID,))
all_types = types_count_df['type'].tolist() if not types_count_df.empty else []
top_4_types = all_types[:4]

if "selected_activities" not in st.session_state:
    st.session_state.selected_activities = top_4_types

# --- 2. UI Layout ---
st.title("Activities Overview")
st.markdown(f"#### :material/person: {athlete_name}")

cols = st.columns([1, 4])

# Mapping display labels to DB columns
metric_map = {
    "Time (hrs)": "duration_hours", 
    "Distance (km)": "distance_km", 
    "Energy (kJ)": "total_kj"
}

with cols[0].container(border=True):
    st.subheader("Filters")

    q_cols = st.columns(2)
    if q_cols[0].button("All", width="stretch"):
        st.session_state.selected_activities = all_types
        st.rerun()
    if q_cols[1].button("Top 4", width="stretch"):
        st.session_state.selected_activities = top_4_types
        st.rerun()
        
    selected_types = st.multiselect("Activities", options=all_types, key="selected_activities")



    st.divider()
    selected_metric_label = st.radio("Metric", options=list(metric_map.keys()))
    selected_metric_col = metric_map[selected_metric_label]

    st.divider()
    horizon_map = {"6 Months": 6, "1 Year": 12, "2 Years": 24, "3 Years": 36, "All Time": 999}
    horizon_label = st.pills("History", options=list(horizon_map.keys()), default="1 Year")

# --- 3. Data Processing ---
# This df contains columns: month, type, activities, duration_hours, distance_km, total_kj
raw_df = run_query_pd(SQL_MONTHLY_ACTIVITY_METRICS, params=(MY_ATHLETE_ID,))

if not raw_df.empty:
    # A. Filter by Activity Type
    df_filtered = raw_df[raw_df['type'].isin(selected_types)].copy()
    
    # B. Ensure 'month' is datetime
    df_filtered['month'] = pd.to_datetime(df_filtered['month'])
    
    # C. Filter by Time Horizon
    if horizon_label != "All Time":
        cutoff = pd.Timestamp.now().normalize() - pd.DateOffset(months=horizon_map[horizon_label])
        df_filtered = df_filtered[df_filtered['month'] >= cutoff]

    with cols[1]:
        # --- 4. Summary Metrics ---
        # We sum the values from the filtered dataframe
        m = st.columns(4)
        m[0].metric("Total Activities", f"{df_filtered['activities'].sum():,}") 
        m[1].metric("Total Time", f"{df_filtered['duration_hours'].sum():,.0f}h")
        m[2].metric("Total Energy", f"{df_filtered['total_kj'].sum():,.0f}kJ")
        m[3].metric("Total Distance", f"{df_filtered['distance_km'].sum():,.0f}km")

        # --- 5. The Chart ---
        with st.container(border=True):
            st.subheader(f"Monthly {selected_metric_label}")
            
            if not df_filtered.empty:
                # Pivot for st.bar_chart: Index = Month, Columns = Activity Types
                # This ensures bars are stacked and colored correctly by Streamlit
                chart_pivot = df_filtered.pivot_table(
                    index='month', 
                    columns='type', 
                    values=selected_metric_col, 
                    aggfunc='sum'
                ).fillna(0)
                
                # We format the index so it doesn't show hours/minutes
                chart_pivot.index = chart_pivot.index.strftime('%Y-%m')
                
                st.bar_chart(
                    chart_pivot,
                    x_label="Month",
                    y_label=selected_metric_label,
                    width="stretch"
                )
            else:
                st.info("No data for the current filter selection.")
else:
    st.info("No activity data found.")