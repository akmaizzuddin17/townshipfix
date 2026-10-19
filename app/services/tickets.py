"""Ticket lifecycle: report -> (merge | new ticket) -> assign -> repair -> verify -> close."""
import json
import secrets
from zoneinfo import ZoneInfo

from .. import clock, config, db
from . import classifier, dedup, notify, priority, text_nlp, verification


class Problem(ValueError):
    """A request we refuse, with a message safe to show the user."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def log(ticket_id, actor, kind, **detail):
    db.ex("INSERT INTO events (ticket_id, at, actor, kind, detail) VALUES (?,?,?,?,?)",
          (ticket_id, clock.iso(clock.now()), actor, kind, json.dumps(detail)))


def get(code):
    t = db.q1("SELECT * FROM tickets WHERE code=?", (code,))
    if not t:
        raise Problem("ticket not found", 404)
    return t


def _next_code():
    n = db.q1("SELECT COUNT(*) AS n FROM tickets")["n"] + 1
    return f"TF-{n:04d}"


def refresh_priority(t):
    n = db.q1("SELECT COUNT(*) AS n FROM reports WHERE ticket_id=?", (t["id"],))["n"]
    p = priority.compute(t["category"], t["flags"] or [], n, t["created_at"], bool(t["urgent"]))
    db.ex("UPDATE tickets SET priority_score=?, priority_band=?, priority_reasons=?, sla_due_at=? WHERE id=?",
          (p["score"], p["band"], json.dumps(p["reasons"]), p["sla_due_at"], t["id"]))
    return p


def sweep():
    """Housekeeping on every read: refresh ageing priority, auto-close silent verified fixes."""
    now = clock.now()
    for t in db.q("SELECT * FROM tickets WHERE status NOT IN ('closed','merged')"):
        if t["status"] == "awaiting_confirmation" and t["completed_at"]:
            if (now - clock.parse(t["completed_at"])).total_seconds() / 3600 >= config.AUTO_CLOSE_HOURS:
                _close(t, "auto_after_verified", "system")
                continue
        refresh_priority(t)


def _close(t, reason, actor, note=None):
    ts = clock.iso(clock.now())
    db.ex("UPDATE tickets SET status='closed', close_reason=?, closed_at=?, updated_at=? WHERE id=?",
          (reason, ts, ts, t["id"]))
    log(t["id"], actor, "closed", reason=reason, note=note)
    notify.residents(get(t["code"]), "closed")


# ------------------------------------------------------------------ intake
def analyse(text, lat, lng, photo_name=None, photo_bytes=None, media_type="image/jpeg", category=None, lang="en"):
    """Everything the resident sees on the read-back screen, before submitting."""
    cls = classifier.classify(text, photo_bytes, media_type)
    cat = category if category in config.CATEGORIES else cls["category"] or "other"
    emergency = text_nlp.detect_emergency(text)
    flags = text_nlp.detect_flags(text)
    match = dedup.find(lat, lng, cat, text, photo_name) if lat is not None else \
        {"action": "new", "ticket": None, "explanation": "no location yet", "all": []}
    return {"suggestion": cls, "category": cat, "emergency": emergency, "flags_detected": flags,
            "match": match}


def create_report(*, text, lat, lng, location_source, landmark, category, flags, lang,
                  photo=None, photo_bytes=None, media_type="image/jpeg", on_behalf_of=None,
                  contact=None, client_duration_ms=None):
    if lat is None or lng is None:
        raise Problem("Location is needed: allow GPS, use a photo with location, or pick an area.")
    if not (text or "").strip() and not photo:
        raise Problem("Please add a photo or describe the problem.")
    if lang not in ("en", "ms"):
        lang = "en"
    a = analyse(text, lat, lng, photo["name"] if photo else None, photo_bytes, media_type, category, lang)
    cat = a["category"]
    all_flags = sorted(set(f for f in (flags or []) if f in config.IMPACT_FLAGS) | set(a["flags_detected"]))
    urgent_reasons = a["emergency"]
    now = clock.iso(clock.now())
    token = secrets.token_hex(16)
    match = a["match"]

    if match["action"] == "merge":
        t = match["ticket"]
        merged = True
        new_flags = sorted(set(t["flags"] or []) | set(all_flags))
        urgent = int(bool(t["urgent"]) or bool(urgent_reasons))
        reasons = sorted(set(t["urgent_reasons"] or []) | set(urgent_reasons))
        db.ex("UPDATE tickets SET flags=?, urgent=?, urgent_reasons=?, updated_at=? WHERE id=?",
              (json.dumps(new_flags), urgent, json.dumps(reasons), now, t["id"]))
        if urgent_reasons and not t["urgent"]:
            notify.security(get(t["code"]), urgent_reasons)
        explanation = "Added to existing ticket " + match["explanation"]
    else:
        merged = False
        team = config.CATEGORIES[cat]["team"]
        title = config.CATEGORIES[cat]["en"]
        tid = db.ex(
            """INSERT INTO tickets (code, category, team, status, lat, lng, landmark, title, flags, urgent,
               urgent_reasons, possible_dup_of, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (_next_code(), cat, team, "open", lat, lng, landmark, title, json.dumps(all_flags),
             int(bool(urgent_reasons)), json.dumps(urgent_reasons),
             match["ticket"]["code"] if match["action"] == "suggest" else None, now, now))
        t = db.q1("SELECT * FROM tickets WHERE id=?", (tid,))
        log(tid, "system", "created", category=cat, team=team)
        if urgent_reasons:
            notify.security(t, urgent_reasons)
        explanation = "New ticket" + (f" (possible duplicate of {match['explanation']}: staff will check)"
                                      if match["action"] == "suggest" else "")

    db.ex("""INSERT INTO reports (ticket_id, token, text, lang, category_chosen, category_suggested, lat, lng,
             location_source, landmark, photo, privacy, flags, on_behalf_of, contact, client_duration_ms,
             merged, merge_explanation, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (t["id"], token, text, lang, category, a["suggestion"]["category"], lat, lng, location_source,
           landmark, photo["name"] if photo else None, json.dumps(photo["privacy"] if photo else {}),
           json.dumps(all_flags), on_behalf_of, contact, client_duration_ms, int(merged), explanation, now))
    log(t["id"], "resident", "report_merged" if merged else "report_received",
        on_behalf=bool(on_behalf_of), explanation=explanation)

    t = get(t["code"])
    p = refresh_priority(t)
    t = get(t["code"])
    n = db.q1("SELECT COUNT(*) AS n FROM reports WHERE ticket_id=?", (t["id"],))["n"]
    if merged:
        notify.residents(t, "merged", n=n)
    else:
        due = clock.parse(p["sla_due_at"]).astimezone(ZoneInfo(config.LOCAL_TZ)).strftime("%d %b, %I:%M %p")
        notify.residents(t, "received", due=due)
        notify.team(t, f"New {t['priority_band']} job {t['code']}: {t['title']} at {landmark or 'map pin'}")
    return {"ticket": public(t), "report_token": token, "merged": merged, "explanation": explanation,
            "reporters": n, "suggestion": a["suggestion"], "dedup": {k: v for k, v in match.items() if k != "ticket"}
            | {"ticket": match["ticket"]["code"] if match["ticket"] else None}}


# ----------------------------------------------------------- staff actions
def assign(code, assignee, actor="staff"):
    t = get(code)
    if t["status"] not in ("open", "assigned"):
        raise Problem(f"cannot assign a ticket that is {t['status']}")
    ts = clock.iso(clock.now())
    db.ex("UPDATE tickets SET status='assigned', assigned_to=?, assigned_at=?, updated_at=? WHERE id=?",
          (assignee or config.TEAMS[t["team"]], ts, ts, t["id"]))
    log(t["id"], actor, "assigned", to=assignee)
    t = get(code)
    notify.residents(t, "assigned")
    return t


def start(code, actor="staff"):
    t = get(code)
    if t["status"] not in ("assigned", "open"):
        raise Problem(f"cannot start work on a ticket that is {t['status']}")
    ts = clock.iso(clock.now())
    db.ex("UPDATE tickets SET status='in_progress', started_at=?, updated_at=? WHERE id=?", (ts, ts, t["id"]))
    log(t["id"], actor, "work_started")
    return get(code)


def complete(code, photo, device_lat=None, device_lng=None, actor="staff"):
    t = get(code)
    if t["status"] not in ("assigned", "in_progress"):
        raise Problem(f"cannot complete a ticket that is {t['status']}")
    result = verification.check(t, photo["name"], photo["exif"], device_lat, device_lng)
    ts = clock.iso(clock.now())
    if result["passed"]:
        db.ex("""UPDATE tickets SET status='awaiting_confirmation', after_photo=?, verification=?,
                 completed_at=?, updated_at=? WHERE id=?""",
              (photo["name"], json.dumps(result), ts, ts, t["id"]))
        log(t["id"], actor, "completion_accepted", checks=result["checks"])
        notify.residents(get(code), "confirm")
    else:
        db.ex("UPDATE tickets SET verification=?, updated_at=? WHERE id=?", (json.dumps(result), ts, t["id"]))
        log(t["id"], actor, "completion_rejected", checks=result["checks"], photo=photo["name"])
    return result


def override_close(code, note, actor="supervisor"):
    t = get(code)
    if t["status"] in ("closed", "merged"):
        raise Problem(f"ticket is already {t['status']}")
    if len((note or "").strip()) < 15:
        raise Problem("A supervisor override needs a written reason (at least 15 characters).")
    _close(t, "supervisor_override", actor, note=note.strip())
    return get(code)


def merge(code, into_code, actor="staff"):
    src, dst = get(code), get(into_code)
    if src["id"] == dst["id"]:
        raise Problem("cannot merge a ticket into itself")
    if src["status"] in ("closed", "merged") or dst["status"] in ("closed", "merged"):
        raise Problem("both tickets must be open")
    ts = clock.iso(clock.now())
    db.ex("UPDATE reports SET ticket_id=?, merged=1, merge_explanation=? WHERE ticket_id=?",
          (dst["id"], f"Merged by staff from {src['code']}", src["id"]))
    flags = sorted(set(src["flags"] or []) | set(dst["flags"] or []))
    db.ex("UPDATE tickets SET flags=?, urgent=?, updated_at=? WHERE id=?",
          (json.dumps(flags), int(src["urgent"] or dst["urgent"]), ts, dst["id"]))
    db.ex("UPDATE tickets SET status='merged', merged_into=?, updated_at=? WHERE id=?", (dst["code"], ts, src["id"]))
    log(src["id"], actor, "merged_into", into=dst["code"])
    log(dst["id"], actor, "merged_from", source=src["code"])
    refresh_priority(get(into_code))
    return get(into_code)


# --------------------------------------------------------- resident actions
def _owns(t, token):
    return token and db.q1("SELECT 1 AS ok FROM reports WHERE ticket_id=? AND token=?", (t["id"], token))


def confirm(code, token):
    t = get(code)
    if not _owns(t, token):
        raise Problem("only a resident who reported this can confirm it", 403)
    if t["status"] != "awaiting_confirmation":
        raise Problem("this ticket is not waiting for confirmation")
    _close(t, "resident_confirmed", "resident")
    return get(code)


def reopen(code, token, reason=""):
    t = get(code)
    if not _owns(t, token):
        raise Problem("only a resident who reported this can reopen it", 403)
    if t["status"] not in ("awaiting_confirmation", "closed"):
        raise Problem("this ticket is still being worked on")
    ts = clock.iso(clock.now())
    db.ex("""UPDATE tickets SET status='assigned', reopen_count=reopen_count+1, close_reason=NULL,
             closed_at=NULL, completed_at=NULL, updated_at=? WHERE id=?""", (ts, t["id"]))
    log(t["id"], "resident", "reopened", reason=(reason or "")[:300])
    t = get(code)
    notify.residents(t, "reopened")
    notify.team(t, f"{code} reopened by resident: {(reason or 'no reason given')[:120]}")
    return t


# ---------------------------------------------------------------- views
def public(t):
    """What anyone with the code may see (no contacts, no tokens)."""
    cat = config.CATEGORIES.get(t["category"], config.CATEGORIES["other"])
    reports = db.q("SELECT photo, created_at FROM reports WHERE ticket_id=? ORDER BY id", (t["id"],))
    events = db.q("SELECT at, kind FROM events WHERE ticket_id=? ORDER BY id", (t["id"],))
    return {
        "code": t["code"], "status": t["status"], "category": t["category"], "category_en": cat["en"],
        "category_ms": cat["ms"], "team": config.TEAMS.get(t["team"], t["team"]), "landmark": t["landmark"],
        "lat": t["lat"], "lng": t["lng"], "priority_band": t["priority_band"], "priority_score": t["priority_score"],
        "urgent": bool(t["urgent"]), "reporters": len(reports), "created_at": t["created_at"],
        "sla_due_at": t["sla_due_at"], "merged_into": t["merged_into"],
        "photos": [r["photo"] for r in reports if r["photo"]], "after_photo": t["after_photo"]
        if t["status"] in ("awaiting_confirmation", "closed") else None,
        "close_reason": t["close_reason"], "timeline": events,
    }


def staff_view(t):
    d = public(t)
    d.update({k: t[k] for k in ("flags", "priority_reasons", "urgent_reasons", "assigned_to", "possible_dup_of",
                                "verification", "reopen_count", "updated_at", "completed_at", "closed_at")})
    d["team_id"] = t["team"]
    d["reports"] = db.q("""SELECT id, text, lang, category_chosen, category_suggested, location_source, landmark,
                           photo, privacy, flags, on_behalf_of, merged, merge_explanation, created_at
                           FROM reports WHERE ticket_id=? ORDER BY id""", (t["id"],))
    d["events"] = db.q("SELECT at, actor, kind, detail FROM events WHERE ticket_id=? ORDER BY id", (t["id"],))
    d["overdue"] = t["status"] not in ("closed", "merged") and bool(t["sla_due_at"]) and \
        clock.now() > clock.parse(t["sla_due_at"])
    return d
