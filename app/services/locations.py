"""Explicit address searches, with offline township areas and a bounded cache.

The public Photon demo is suitable for a small hackathon demo, not a service
with an availability guarantee. Configure a private Photon endpoint for a pilot.
"""
import math
import threading
import time
from collections import OrderedDict

import requests

from .. import config

_cache = OrderedDict()
_lock = threading.Lock()
_last_request = float("-inf")


def search(query):
    query = " ".join(query.split())
    words = query.casefold().split()
    local = [{"label": z["name"], "lat": z["lat"], "lng": z["lng"],
              "source": "zone", "zone": z["id"]}
             for z in config.ZONES if all(w in z["name"].casefold() for w in words)]
    if local or not config.GEOCODER_URL:
        return {"items": local, "unavailable": False}

    # Do not build a queue of external requests. This also protects the demo
    # provider against repeated button presses and simultaneous users.
    key = (config.GEOCODER_URL, query.casefold())
    with _lock:
        cached = _cache.get(key)
        if cached and time.monotonic() - cached[0] < 600:
            _cache.move_to_end(key)
            return {"items": cached[1], "unavailable": False}
        global _last_request
        now = time.monotonic()
        if now - _last_request < 1:
            return {"items": [], "unavailable": True}
        _last_request = now

    try:
        response = requests.get(
            config.GEOCODER_URL,
            params={"q": query, "limit": 5, "lang": "en",
                    "lat": config.ZONES[0]["lat"] if config.ZONES else 3.14,
                    "lon": config.ZONES[0]["lng"] if config.ZONES else 101.69},
            headers={"User-Agent": "TownshipFix/1.0 (+https://github.com/akmaizzuddin17/townshipfix)"},
            timeout=15,
        )
        response.raise_for_status()
        items = []
        for feature in response.json().get("features", [])[:5]:
            try:
                lng, lat = map(float, feature["geometry"]["coordinates"][:2])
                if not (math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180):
                    continue
                p = feature.get("properties") or {}
                parts = [str(p[k]) for k in ("name", "housenumber", "street", "district", "city", "state", "country") if p.get(k)]
                label = ", ".join(dict.fromkeys(parts))[:300]
                if label:
                    items.append({"label": label, "lat": lat, "lng": lng, "source": "address_search"})
            except (KeyError, TypeError, ValueError):
                continue
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return {"items": [], "unavailable": True}

    with _lock:
        _cache[key] = (time.monotonic(), items)
        _cache.move_to_end(key)
        while len(_cache) > 128:
            _cache.popitem(last=False)
    return {"items": items, "unavailable": False}
