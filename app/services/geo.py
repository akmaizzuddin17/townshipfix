import math


def distance_m(lat1, lng1, lat2, lng2):
    """Great-circle distance in metres (haversine)."""
    if None in (lat1, lng1, lat2, lng2):
        return None
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
