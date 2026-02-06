# scripts/backfill_map_data.py

from core.database import get_db_connection, run_query
from core.map_utils import process_activity_map
from config import MAP_SUMMARY_TOLERANCE

def backfill_activities():
    # 1. Fetch activities that need processing
    # Using run_query which returns a list of RealDictCursor dictionaries
    query_find = """
        SELECT strava_id, map_polyline 
        FROM activities 
        WHERE map_polyline IS NOT NULL 
        AND min_lat IS NULL;
    """
    rows = run_query(query_find)
    
    if not rows:
        print("No activities found that require backfilling.")
        return

    print(f"Found {len(rows)} activities to process with tolerance {MAP_SUMMARY_TOLERANCE}")

    # 2. Use a single connection for the batch update
    conn = get_db_connection()
    processed_count = 0
    
    try:
        with conn.cursor() as cur:
            for ride in rows:
                strava_id = ride['strava_id']
                raw_polyline = ride['map_polyline']
                
                # Generate summary and bounding box
                summary, min_lat, max_lat, min_lng, max_lng = process_activity_map(
                    raw_polyline, 
                    tolerance=MAP_SUMMARY_TOLERANCE
                )
                
                # Update the row
                cur.execute("""
                    UPDATE activities 
                    SET summary_polyline = %s,
                        min_lat = %s,
                        max_lat = %s,
                        min_lng = %s,
                        max_lng = %s
                    WHERE strava_id = %s;
                """, (summary, min_lat, max_lat, min_lng, max_lng, strava_id))
                
                processed_count += 1
                if processed_count % 100 == 0:
                    print(f"Processed {processed_count}...")
            
            # Commit all changes at the end
            conn.commit()
            print(f"✅ Successfully backfilled {processed_count} activities.")
            
    except Exception as e:
        conn.rollback()
        print(f"❌ Error during backfill: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    backfill_activities()