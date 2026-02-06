import psycopg2
import sys
from core.map_utils import process_activity_map
from config import DB_NAME, DB_USER, DB_PASS, DB_HOST, DB_PORT

def test_single_ride(tolerance):
    # 1. Connect to your local mirrored DB
    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT
    )
    cur = conn.cursor()

    # 2. Get the specific ride
    cur.execute("SELECT strava_id, name, map_polyline FROM activities WHERE strava_id = 16696125832;")
    ride = cur.fetchone()
    
    if not ride:
        print("No ride with ID 16696125832 found!")
        return

    strava_id, name, raw_polyline = ride
    
    # 3. Process with the tolerance passed from terminal
    summary, min_lat, max_lat, min_lng, max_lng = process_activity_map(raw_polyline, tolerance=tolerance)
    
    # 4. Compare results
    before_len = len(raw_polyline)
    after_len = len(summary)
    reduction = ((before_len - after_len) / before_len) * 100

    print(f"--- Running with Tolerance: {tolerance} ---")
    print(f"Ride: {name} ({strava_id})")
    print(f"Original Length: {before_len} chars")
    print(f"Summary Length:  {after_len} chars")
    print(f"Reduction:       {reduction:.2f}%")
    print(f"Bounding Box:    ({min_lat:.4f}, {min_lng:.4f}) to ({max_lat:.4f}, {max_lng:.4f})")

    cur.close()
    conn.close()

if __name__ == "__main__":
    # Check if a parameter was provided, otherwise default to 0.0001
    try:
        t_val = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0001
    except ValueError:
        print("Invalid tolerance provided. Using default 0.0001")
        t_val = 0.0001
        
    test_single_ride(tolerance=t_val)