# core/laps.py
from core.database import run_query
from datetime import datetime

def merge_activity_laps(strava_id, lap_ids):
    """
    Merges multiple laps into one by calculating weighted averages.
    Uses unique lap_id to ensure precision.
    """

    print(f"DEBUG: Received strava_id: {strava_id} (Type: {type(strava_id)})")
    print(f"DEBUG: Received lap_ids: {lap_ids}")

    try:
        lap_ids = [int(lid) for lid in lap_ids]
    except (ValueError, TypeError):
        return False, "Invalid lap IDs provided."
    
    # 1. Fetch the laps to be merged using unique lap_ids
    laps = run_query("""
        SELECT * FROM activity_laps 
        WHERE strava_id = %s AND lap_id = ANY(%s) 
        ORDER BY start_index ASC
    """, (strava_id, lap_ids))

    print(f"DEBUG: Database found {len(laps) if laps else 0} laps matching those IDs.")

    if len(laps) < 2:
        return False, "Select at least two laps to merge."

    # 2. Aggregate Data (Weighted by moving_time)
    total_mov_t = sum(float(l['moving_time']) for l in laps)
    if total_mov_t == 0:
        return False, "Moving time cannot be zero."

    total_dist = sum(float(l['distance']) for l in laps)
    total_ela_t = sum(float(l['elapsed_time']) for l in laps)
    total_elev = sum(float(l['total_elevation_gain']) for l in laps)
    
    # Math: (Value * Time) / Total Time
    avg_w = sum(float(l['average_watts'] or 0) * float(l['moving_time']) for l in laps) / total_mov_t
    avg_hr = sum(float(l['average_heartrate'] or 0) * float(l['moving_time']) for l in laps) / total_mov_t
    avg_cad = sum(float(l['average_cadence'] or 0) * float(l['moving_time']) for l in laps) / total_mov_t

    # Bounds & New Properties
    start_idx = laps[0]['start_index']
    end_idx = laps[-1]['end_index']
    start_date = laps[0]['start_date_local']
    
    # We maintain the lap_index of the first lap in the selection
    new_lap_index = laps[0]['lap_index'] 
    
    try:
        # 3. Create the New Manual Lap
        # Generate a unique manual_id using timestamp to avoid collisions
        now = datetime.now()
        manual_id = int(f"{strava_id}{now.strftime('%M%S%f')}"[:15])

        insert_sql = """
            INSERT INTO activity_laps (
                lap_id, strava_id, lap_index, start_index, end_index, name, 
                distance, moving_time, elapsed_time, total_elevation_gain,
                average_watts, average_heartrate, average_cadence, 
                is_manual, is_hidden, start_date_local
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, FALSE, %s)
        """
        run_query(insert_sql, (
            manual_id, strava_id, new_lap_index, start_idx, end_idx, 
            f"Merged {laps[0]['lap_index']}-{laps[-1]['lap_index']}",
            total_dist, total_mov_t, total_ela_t, total_elev,
            avg_w, avg_hr, avg_cad, start_date
        ))

        # 4. Hide exactly what we merged
        # We don't filter by is_manual here because you might want to merge a 
        # previously merged lap with another one.
        run_query("""
            UPDATE activity_laps 
            SET is_hidden = TRUE 
            WHERE strava_id = %s AND lap_id = ANY(%s)
        """, (strava_id, lap_ids))

        return True, "Laps merged successfully."
    except Exception as e:
        return False, f"Merge failed: {str(e)}"

def reset_activity_laps(strava_id):
    """Deletes manual laps and unhides original Strava laps."""
    try:
        run_query("DELETE FROM activity_laps WHERE strava_id = %s AND is_manual = TRUE", (strava_id,))
        run_query("UPDATE activity_laps SET is_hidden = FALSE WHERE strava_id = %s", (strava_id,))
        return True, "Laps reset to original."
    except Exception as e:
        return False, str(e)