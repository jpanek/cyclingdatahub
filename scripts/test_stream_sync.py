# scripts/test_stream_sync.py

import sys
import os

# Add root to path so we can import core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.database import get_db_connection, run_query
from core.strava_api import sync_activity_streams

from config import MY_ATHLETE_ID

# this will backfill activity sterams for listed activities:

activity_ids = [
    16630530621, 16639969032, 16650668038, 16666792036, 
    16685554700, 16696125832, 16704367490, 16706577984, 
    16714005315, 16723332640, 16733410425, 16743814470, 
    16758811931, 16759965047, 16768311119, 16769918643, 
    16776825414, 16777732565, 16785726790, 16794671068, 
    16800997956, 16803624335, 16804313501, 16811952837, 
    16819379294, 16873641837, 16926446579
]

print(len(activity_ids))
print(min(activity_ids))

#sys.exit()

conn = get_db_connection()

for activity_id in activity_ids:
    print(f"\t🚀 Starting sync for Activity: {activity_id}...")
    sync_activity_streams(conn, MY_ATHLETE_ID, activity_id)
