# scripts/backfill_activities.py


"""
# run me like:
cd /path/to/your/vps/project
source venv/bin/activate
python -m scripts.backfill_activities 12689416 10
"""

import sys
from core.database import get_db_connection, save_db_activities
from core.strava_api import get_valid_access_token, fetch_activities_list

def backfill_metadata(athlete_id, max_pages=10):
    conn = get_db_connection()
    try:
        print(f"\n🚀 Starting metadata backfill for Athlete: {athlete_id}")
        
        # 1. Auth
        tokens_dict = get_valid_access_token(conn, athlete_id)
        token = tokens_dict['access_token']
        
        total_saved = 0
        # We start at page 1 and go back in time
        for page in range(1, max_pages + 1):
            print(f"\tFetching page {page}...")
            
            params = {
                "page": page,
                "per_page": 200
            }
            
            activities = fetch_activities_list(token, params)
            
            if not activities:
                print(f"\t🏁 No more activities found on page {page}.")
                break
            
            # 2. Save to DB 
            # save_db_activities handles the "ON CONFLICT DO NOTHING/UPDATE" logic
            save_db_activities(conn, athlete_id, activities)
            
            total_saved += len(activities)
            print(f"\t✅ Saved {len(activities)} activities from page {page}.")

        print(f"\n✨ Backfill complete. Total activities processed: {total_saved}")

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
    finally:
        conn.close()

if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage: python -m scripts.backfill_activities <athlete_id> [max_pages]")
        sys.exit(1)
        
    a_id = int(sys.argv[1])
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    
    backfill_metadata(a_id, pages)