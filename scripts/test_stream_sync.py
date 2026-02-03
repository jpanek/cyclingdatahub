# scripts/test_stream_sync.py

import sys
import os
import time

# Add root to path so we can import core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.database import get_db_connection, run_query
from core.strava_api import sync_activity_streams

from config import MY_ATHLETE_ID

# this will backfill activity sterams for listed activities:

activity_ids = [
    15137590270, 15100546832,
    15072497852, 15061887584, 15045983506, 15035189222, 15026239059,
    15017325763, 15007431325, 15005987925, 14997615303, 14987911230,
    14973794401, 14964692427, 14962469647, 14953406469, 14945744267,
    14945741164, 14933981969, 14921632858, 14915952204, 14902206048,
    14890238663, 14881402325, 14873188215, 14868837286, 14853114755,
    14849570888, 14842607512, 14828068309, 14810361163, 14796973797,
    14788784048, 14775698055, 14769940109, 14757131570, 14746176528,
    14736419915, 14722028207, 14715447640, 14703548672, 14695670813,
    14685512638, 14673164718, 14661928038, 14652809531, 14643482294,
    14632333419, 14610303635, 14600440332, 14590554406, 14579139495
]

#sys.exit()

conn = get_db_connection()

for activity_id in activity_ids:
    print(f"\t🚀 Starting sync for Activity: {activity_id}...")
    sync_activity_streams(conn, MY_ATHLETE_ID, activity_id,force=False)
    time.sleep(5)
