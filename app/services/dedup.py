"""Groups reports about the same problem into one ticket.

For each open ticket nearby we combine:
  geo   - how close (1.0 at the same spot, 0 at DEDUP_RADIUS_M)
  cat   - same category 1.0, related category 0.5, unrelated 0
  image - same-scene photo match (SIFT + geometry), when both have photos
  text  - shared words (minor signal, used only without photos)
and return a decision with a plain-language explanation.
"""
from .. import config, db
from . import geo, photos, text_nlp, vision

OPEN = ("open", "assigned", "in_progress", "awaiting_confirmation")


def _cat_score(a, b):
    if a == b:
        return 1.0
    ga = config.CATEGORIES.get(a, {}).get("group")
    gb = config.CATEGORIES.get(b, {}).get("group")
    return 0.5 if ga and ga == gb and ga != "other" else 0.0


def _words(t):
    return {w for w in text_nlp.normalise(t).split() if len(w) > 2}


def _text_score(a, b):
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def candidates(lat, lng):
    out = []
    for t in db.q("SELECT * FROM tickets WHERE status IN (%s)" % ",".join("?" * len(OPEN)), OPEN):
        d = geo.distance_m(lat, lng, t["lat"], t["lng"])
        if d is not None and d <= config.DEDUP_RADIUS_M:
            out.append((d, t))
    return sorted(out, key=lambda x: x[0])


def score_against(ticket, dist, category, text, photo_name):
    reports = db.q("SELECT text, photo FROM reports WHERE ticket_id=? ORDER BY id DESC LIMIT 6",
                   (ticket["id"],))
    g = max(0.0, 1.0 - dist / config.DEDUP_RADIUS_M)
    c = _cat_score(category, ticket["category"])
    img = None
    if photo_name:
        fa = photos.features(photo_name)
        best = None
        for r in reports:
            if r["photo"]:
                s = vision.photo_similarity(fa, photos.features(r["photo"]))
                if best is None or s["score"] > best["score"]:
                    best = s
        img = best
    txt = max([_text_score(text, r["text"]) for r in reports] or [0.0])
    if img is not None:
        total = 0.35 * g + 0.25 * c + 0.40 * img["score"]
        if img["score"] >= config.DEDUP_STRONG_IMAGE:
            total = max(total, config.DEDUP_MERGE_SCORE)  # same scene; category was likely mis-tapped
        elif c == 0:
            total = min(total, config.DEDUP_SUGGEST_SCORE - 0.01)  # unrelated types: separate tickets
        elif img["score"] < config.DEDUP_DIFFERENT_SCENE and dist > config.DEDUP_NO_PHOTO_RADIUS_M:
            # photos clearly show a different spot and it is not right next to it
            total = min(total, config.DEDUP_SUGGEST_SCORE - 0.01)
    else:
        total = 0.55 * g + 0.35 * c + 0.10 * txt
        if c == 0:
            total = min(total, config.DEDUP_SUGGEST_SCORE - 0.01)
        elif dist > config.DEDUP_NO_PHOTO_RADIUS_M or c < 1.0:
            total = min(total, config.DEDUP_SUGGEST_SCORE)  # let staff decide
    return {"total": round(total, 3), "geo": round(g, 3), "category": c,
            "image": img, "text": round(txt, 3), "distance_m": round(dist, 1)}


def explain(ticket, s, lang="en"):
    parts = [f"{s['distance_m']:.0f} m away"]
    if s["category"] == 1.0:
        parts.append("same type of problem")
    elif s["category"] == 0.5:
        parts.append("related type of problem")
    if s["image"] is not None:
        parts.append(f"photo match {int(round(s['image']['score'] * 100))}%")
    return f"{ticket['code']}: " + ", ".join(parts)


def find(lat, lng, category, text, photo_name):
    """Return {'action': merge|suggest|new, 'ticket', 'score', 'explanation', 'all'}."""
    scored = []
    for dist, t in candidates(lat, lng):
        s = score_against(t, dist, category, text, photo_name)
        scored.append((s["total"], t, s))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        return {"action": "new", "ticket": None, "score": None, "explanation": "no open tickets nearby",
                "all": []}
    total, t, s = scored[0]
    summary = [{"code": tt["code"], **{k: v for k, v in ss.items() if k != "image"},
                "image_score": ss["image"]["score"] if ss["image"] else None} for _, tt, ss in scored[:5]]
    if total >= config.DEDUP_MERGE_SCORE:
        action = "merge"
    elif total >= config.DEDUP_SUGGEST_SCORE:
        action = "suggest"
    else:
        action = "new"
    return {"action": action, "ticket": t, "score": s, "explanation": explain(t, s), "all": summary}
