# core/map_utils.py

import polyline
import math

def point_line_distance(point, start, end):
    """Calculates the perpendicular distance of a point from a line."""
    if start == end:
        return math.sqrt((point[0] - start[0])**2 + (point[1] - start[1])**2)

    # Standard formula for distance from point to line segment
    n = abs((end[0] - start[0]) * (start[1] - point[1]) - (start[0] - point[0]) * (end[1] - start[1]))
    d = math.sqrt((end[0] - start[0])**2 + (end[1] - start[1])**2)
    return n / d

def rdp_simplify(coords, tolerance):
    """
    Ramer-Douglas-Peucker algorithm for path simplification.
    """
    if len(coords) < 3:
        return coords

    dmax = 0
    index = 0
    end = len(coords) - 1

    for i in range(1, end):
        d = point_line_distance(coords[i], coords[0], coords[end])
        if d > dmax:
            index = i
            dmax = d

    if dmax > tolerance:
        # Recursive call
        left = rdp_simplify(coords[:index+1], tolerance)
        right = rdp_simplify(coords[index:], tolerance)
        return left[:-1] + right
    else:
        return [coords[0], coords[end]]

def get_bounding_box(coords):
    if not coords:
        return None, None, None, None
    lats = [c[0] for c in coords]
    lngs = [c[1] for c in coords]
    return min(lats), max(lats), min(lngs), max(lngs)

def process_activity_map(raw_polyline, tolerance=0.1):
    """
    The main worker. 
    Tolerance 0.0001 is ~11m. Use 0.00005 for ~5m.
    """
    if not raw_polyline:
        return None, None, None, None, None
    
    coords = polyline.decode(raw_polyline)
    
    # 1. Get Bounding Box (Always from raw data for precision)
    min_lat, max_lat, min_lng, max_lng = get_bounding_box(coords)
    
    # 2. Simplify using RDP
    simplified_coords = rdp_simplify(coords, tolerance)
    
    # 3. Re-encode
    summary_polyline = polyline.encode(simplified_coords)
    
    return summary_polyline, min_lat, max_lat, min_lng, max_lng