"""Checks a contractor's 'after' photo before a ticket can close.

A repair is accepted only if every check passes:
  1. Same place   - the after photo matches the residents' photos (scene geometry)
  2. Real change  - part of the scene looks different, but not all of it
  3. Not a re-upload - it is not just one of the residents' photos again
  4. Taken after the report - if the photo carries a capture time
  5. Taken nearby - if the photo or phone gave a location
Then the resident who reported it is asked to confirm (or reopen).
"""
from datetime import timedelta

from .. import clock, config, db
from . import geo, photos, vision


def check(ticket, after_name, after_exif, device_lat=None, device_lng=None):
    reports = db.q("SELECT photo FROM reports WHERE ticket_id=? AND photo IS NOT NULL", (ticket["id"],))
    checks = []
    fa = photos.features(after_name)

    # 3. re-upload / near-identical
    best = None
    for r in reports:
        fb = photos.features(r["photo"])
        sim = vision.photo_similarity(fa, fb)
        if best is None or sim["inliers"] > best[1]["inliers"]:
            best = (r["photo"], sim, fb)
    if not reports:
        checks.append({"id": "same_place", "ok": None,
                       "detail": "No resident photo to compare with: needs supervisor review"})
    else:
        before_name, sim, fb = best
        identical = sim["dhash"] >= 0.98 and sim["hist"] >= 0.98
        # 1. same place
        same = sim["geom"] >= config.VERIFY_MIN_SCENE
        checks.append({"id": "same_place", "ok": same,
                       "detail": f"Scene match {int(sim['geom'] * 100)}% ({sim['inliers']} matching points)"
                       + ("" if same else ": does not look like the reported spot")})
        # 2. real change
        if same:
            frac, info = vision.change_fraction(photos.load_cv(before_name), photos.load_cv(after_name), fb, fa)
            if frac is None:
                checks.append({"id": "changed", "ok": False, "detail": "Could not line the photos up to compare"})
            else:
                ok = config.VERIFY_MIN_CHANGE <= frac <= config.VERIFY_MAX_CHANGE and not identical
                if identical or frac < config.VERIFY_MIN_CHANGE:
                    why = "nothing visibly changed"
                elif frac > config.VERIFY_MAX_CHANGE:
                    why = "almost everything differs: likely a different view"
                else:
                    why = "the problem area looks different"
                checks.append({"id": "changed", "ok": ok,
                               "detail": f"{int(round(frac * 100))}% of the scene changed: {why}"})
        else:
            checks.append({"id": "changed", "ok": False, "detail": "Skipped because the place did not match"})
        checks.append({"id": "not_reupload", "ok": not identical,
                       "detail": "Same image as a resident's photo" if identical else "New photo"})

    # 4. time
    created = clock.parse(ticket["created_at"])
    if after_exif.get("taken_at"):
        ok = after_exif["taken_at"] >= created - timedelta(minutes=5)
        checks.append({"id": "taken_after", "ok": ok,
                       "detail": "Photo taken after the report" if ok else "Photo was taken BEFORE the report"})
    else:
        checks.append({"id": "taken_after", "ok": None, "detail": "No capture time in photo (upload time used)"})

    # 5. location
    lat = after_exif.get("lat") if after_exif.get("lat") is not None else device_lat
    lng = after_exif.get("lng") if after_exif.get("lng") is not None else device_lng
    d = geo.distance_m(lat, lng, ticket["lat"], ticket["lng"])
    if d is None:
        checks.append({"id": "nearby", "ok": None, "detail": "No location with photo"})
    else:
        ok = d <= config.VERIFY_MAX_DISTANCE_M
        checks.append({"id": "nearby", "ok": ok, "detail": f"Taken {d:.0f} m from the reported spot"})

    hard_fail = [c for c in checks if c["ok"] is False]
    unknown_core = [c for c in checks if c["id"] == "same_place" and c["ok"] is None]
    passed = not hard_fail and not unknown_core
    return {"passed": passed, "checks": checks, "after_photo": after_name, "at": clock.iso(clock.now()),
            "summary": "Repair evidence accepted: waiting for resident to confirm" if passed else
                       "Repair evidence rejected: " + "; ".join(c["detail"] for c in hard_fail + unknown_core)}
