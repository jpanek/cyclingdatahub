# core/laps.py
from core.database import run_query
from datetime import datetime

def merge_activity_laps(strava_id, lap_indices):
    """
    Merges multiple laps into one by calculating weighted averages.
    Uses database.py run_query for transaction safety.
    """
    # 1. Fetch the laps to be merged
    # We use lap_index because lap_id is a unique big-int from Strava 
    # and might not be sequential in your mind, but lap_index is.
    laps = run_query("""
        SELECT * FROM activity_laps 
        WHERE strava_id = %s AND lap_index = ANY(%s) 
        ORDER BY start_index ASC
    """, (strava_id, lap_indices))

    if len(laps) < 2:
        return False, "Select at least two laps to merge."

    # 2. Aggregate Data (Weighted by moving_time)
    total_mov_t = sum(float(l['moving_time']) for l in laps)
    if total_mov_t == 0:
        return False, "Moving time cannot be zero."

    total_dist = sum(float(l['distance']) for l in laps)
    total_ela_t = sum(float(l['elapsed_time']) for l in laps)
    total_elev = sum(float(l['total_elevation_gain']) for l in laps)
    
    # Math: (Value1 * Time1 + Value2 * Time2) / Total Time
    avg_w = sum(float(l['average_watts']) * float(l['moving_time']) for l in laps) / total_mov_t
    avg_hr = sum(float(l['average_heartrate']) * float(l['moving_time']) for l in laps) / total_mov_t
    avg_cad = sum(float(l['average_cadence']) * float(l['moving_time']) for l in laps) / total_mov_t

    # Bounds
    start_idx = laps[0]['start_index']
    end_idx = laps[-1]['end_index']
    start_date = laps[0]['start_date_local']
    new_lap_index = laps[0]['lap_index'] # We take the first one's index
    
    try:
        # 3. Create the New Manual Lap
        # lap_id needs a value. Since it's a manual lap, we can generate a 
        # fake ID based on strava_id + timestamp to avoid collision.
        manual_id = int(f"{strava_id}{int(datetime.now().timestamp())}"[:15])

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
            f"Merged {laps[0]['name']}+{laps[-1]['name']}",
            total_dist, total_mov_t, total_ela_t, total_elev,
            avg_w, avg_hr, avg_cad, start_date
        ))

        # 4. Hide the originals
        run_query("""
            UPDATE activity_laps 
            SET is_hidden = TRUE 
            WHERE strava_id = %s AND lap_index = ANY(%s) AND is_manual = FALSE
        """, (strava_id, lap_indices))

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