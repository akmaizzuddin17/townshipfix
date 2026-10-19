import re
import secrets
import shutil

from flask import Blueprint, abort, current_app, jsonify, request, send_from_directory

from . import clock, config, db
from .services import metrics, photos, privacy, tickets
from .services.photos import PhotoError
from .services.tickets import Problem

bp = Blueprint("api", __name__)
PHOTO_RE = re.compile(r"^[ra]_[0-9a-f]{12}\.jpg$")


# ------------------------------------------------------------- helpers
def _num(v, name, lo, hi):
    if v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise Problem(f"{name} must be a number")
    if not lo <= f <= hi:
        raise Problem(f"{name} out of range")
    return f


def _photo_ref(ref):
    if not ref:
        return None
    if not PHOTO_RE.match(ref) or not (config.UPLOAD_DIR / ref).exists():
        raise Problem("photo not found: please add it again")
    return {"name": ref, "privacy": db_photo_privacy.get(ref, {"exif_removed": True})}


# privacy info for photos uploaded in this server run (kept small; also stored on the report)
db_photo_privacy = {}


def _staff():
    pin = request.headers.get("X-Staff-Pin", "")
    if not secrets.compare_digest(pin, config.STAFF_PIN):
        abort(401)


@bp.errorhandler(Problem)
def _problem(e):
    return jsonify(error=str(e)), e.status


@bp.errorhandler(PhotoError)
def _photo_problem(e):
    return jsonify(error=str(e)), 400


@bp.errorhandler(401)
def _unauth(_):
    return jsonify(error="staff PIN required"), 401


@bp.errorhandler(404)
def _nf(_):
    return jsonify(error="not found"), 404


@bp.errorhandler(413)
def _too_big(_):
    return jsonify(error=f"photo larger than {config.MAX_UPLOAD_MB} MB"), 413


# --------------------------------------------------------------- pages
@bp.get("/")
def resident_page():
    return send_from_directory(current_app.static_folder, "index.html")


@bp.get("/staff")
def staff_page():
    return send_from_directory(current_app.static_folder, "staff.html")


@bp.get("/media/<name>")
def media(name):
    if not PHOTO_RE.match(name):
        abort(404)
    return send_from_directory(config.UPLOAD_DIR, name, max_age=3600)


# ------------------------------------------------------------ resident
@bp.get("/api/config")
def get_config():
    return jsonify(categories=config.CATEGORIES, flags=config.IMPACT_FLAGS, zones=config.ZONES,
                   teams=config.TEAMS, vision=tickets.classifier._provider(),
                   privacy_detectors=privacy.detectors_available())


@bp.post("/api/photos")
def upload_photo():
    f = request.files.get("photo")
    if not f:
        raise Problem("no photo attached")
    stored = photos.store(f.read(), prefix="r")
    db_photo_privacy[stored["name"]] = stored["privacy"]
    ex = stored["exif"]
    return jsonify(ref=stored["name"], url=f"/media/{stored['name']}", privacy=stored["privacy"],
                   gps={"lat": ex["lat"], "lng": ex["lng"]} if ex["lat"] is not None else None,
                   taken_at=clock.iso(ex["taken_at"]) if ex["taken_at"] else None)


def _place(data):
    lat = _num(data.get("lat"), "lat", -90, 90)
    lng = _num(data.get("lng"), "lng", -180, 180)
    zone = next((z for z in config.ZONES if z["id"] == data.get("zone")), None)
    landmark = (data.get("landmark") or "").strip()[:120] or (zone["name"] if zone else None)
    source = data.get("location_source") or ("zone" if zone and lat is None else "device_gps")
    if lat is None and zone:
        lat, lng = zone["lat"], zone["lng"]
    return lat, lng, landmark, source


@bp.post("/api/analyze")
def analyze():
    data = request.get_json(silent=True) or {}
    lat, lng, landmark, _ = _place(data)
    photo = _photo_ref(data.get("photo_ref"))
    text = (data.get("text") or "")[:1000]
    lang = data.get("lang") if data.get("lang") in ("en", "ms") else "en"
    pb = (config.UPLOAD_DIR / photo["name"]).read_bytes() if photo else None
    a = tickets.analyse(text, lat, lng, photo["name"] if photo else None, pb, "image/jpeg",
                        data.get("category"), lang)
    m = a["match"]
    place = landmark or ("your pinned location" if lang == "en" else "lokasi anda")
    return jsonify(
        suggestion=a["suggestion"], category=a["category"], emergency=a["emergency"],
        flags_detected=a["flags_detected"],
        readback=tickets.text_nlp.readback(a["category"], place, lang, bool(a["emergency"])),
        match={"action": m["action"], "explanation": m["explanation"],
               "ticket": tickets.public(m["ticket"]) if m["ticket"] and m["action"] != "new" else None},
    )


@bp.post("/api/reports")
def create_report():
    data = request.get_json(silent=True) or {}
    lat, lng, landmark, source = _place(data)
    photo = _photo_ref(data.get("photo_ref"))
    flags = data.get("flags") or []
    if not isinstance(flags, list):
        raise Problem("flags must be a list")
    dur = data.get("client_duration_ms")
    dur = int(dur) if isinstance(dur, (int, float)) and 0 < dur < 3_600_000 else None
    res = tickets.create_report(
        text=(data.get("text") or "")[:1000], lat=lat, lng=lng, location_source=source, landmark=landmark,
        category=data.get("category") if data.get("category") in config.CATEGORIES else None,
        flags=[str(f) for f in flags], lang=data.get("lang", "en"), photo=photo,
        photo_bytes=(config.UPLOAD_DIR / photo["name"]).read_bytes() if photo else None,
        on_behalf_of=(data.get("on_behalf_of") or "").strip()[:80] or None,
        contact=(data.get("contact") or "").strip()[:40] or None, client_duration_ms=dur)
    return jsonify(res), 201


@bp.get("/api/tickets/<code>")
def ticket_status(code):
    tickets.sweep()
    t = tickets.get(code.upper())
    return jsonify(tickets.public(t))


@bp.post("/api/my")
def my_reports():
    data = request.get_json(silent=True) or {}
    toks = [t for t in (data.get("tokens") or []) if isinstance(t, str)][:50]
    tickets.sweep()
    out = []
    for tok in toks:
        r = db.q1("SELECT ticket_id, created_at FROM reports WHERE token=?", (tok,))
        if r:
            t = db.q1("SELECT * FROM tickets WHERE id=?", (r["ticket_id"],))
            if t["status"] == "merged" and t["merged_into"]:
                t = tickets.get(t["merged_into"])
            out.append({"token": tok, "reported_at": r["created_at"], "ticket": tickets.public(t)})
    return jsonify(items=out)


@bp.post("/api/tickets/<code>/confirm")
def confirm(code):
    data = request.get_json(silent=True) or {}
    return jsonify(tickets.public(tickets.confirm(code.upper(), data.get("token"))))


@bp.post("/api/tickets/<code>/reopen")
def reopen(code):
    data = request.get_json(silent=True) or {}
    return jsonify(tickets.public(tickets.reopen(code.upper(), data.get("token"), data.get("reason", ""))))


# ---------------------------------------------------------------- staff
@bp.get("/api/staff/tickets")
def staff_tickets():
    _staff()
    tickets.sweep()
    which = request.args.get("status", "active")
    rows = db.q("SELECT * FROM tickets ORDER BY urgent DESC, priority_score DESC, created_at ASC")
    if which == "active":
        rows = [t for t in rows if t["status"] not in ("closed", "merged")]
    elif which != "all":
        rows = [t for t in rows if t["status"] == which]
    return jsonify(items=[tickets.staff_view(t) for t in rows])


@bp.get("/api/staff/tickets/<code>")
def staff_ticket(code):
    _staff()
    return jsonify(tickets.staff_view(tickets.get(code.upper())))


@bp.post("/api/staff/tickets/<code>/assign")
def staff_assign(code):
    _staff()
    data = request.get_json(silent=True) or {}
    return jsonify(tickets.staff_view(tickets.assign(code.upper(), (data.get("assignee") or "").strip()[:60])))


@bp.post("/api/staff/tickets/<code>/start")
def staff_start(code):
    _staff()
    return jsonify(tickets.staff_view(tickets.start(code.upper())))


@bp.post("/api/staff/tickets/<code>/complete")
def staff_complete(code):
    _staff()
    f = request.files.get("photo")
    if not f:
        raise Problem("an after photo is required to complete a job")
    tickets.get(code.upper())  # 404 before storing anything
    stored = photos.store(f.read(), prefix="a")
    lat = _num(request.form.get("lat"), "lat", -90, 90)
    lng = _num(request.form.get("lng"), "lng", -180, 180)
    result = tickets.complete(code.upper(), stored, lat, lng)
    return jsonify(result=result, ticket=tickets.staff_view(tickets.get(code.upper())))


@bp.post("/api/staff/tickets/<code>/override")
def staff_override(code):
    _staff()
    data = request.get_json(silent=True) or {}
    return jsonify(tickets.staff_view(tickets.override_close(code.upper(), data.get("note", ""))))


@bp.post("/api/staff/tickets/<code>/merge")
def staff_merge(code):
    _staff()
    data = request.get_json(silent=True) or {}
    return jsonify(tickets.staff_view(tickets.merge(code.upper(), (data.get("into") or "").upper())))


@bp.get("/api/staff/metrics")
def staff_metrics():
    _staff()
    tickets.sweep()
    return jsonify(metrics.compute())


@bp.get("/api/staff/outbox")
def staff_outbox():
    _staff()
    return jsonify(items=db.q("""SELECT o.*, t.code FROM outbox o LEFT JOIN tickets t ON t.id=o.ticket_id
                                 ORDER BY o.id DESC LIMIT 100"""))


@bp.post("/api/staff/reset")
def staff_reset():
    """Wipe all demo data (tickets, reports, photos)."""
    _staff()
    db.reset_connection()
    for p in (config.DB_PATH,):
        if p.exists():
            p.unlink()
    for d in (config.UPLOAD_DIR, config.FEATURE_DIR):
        shutil.rmtree(d, ignore_errors=True)
    db_photo_privacy.clear()
    db.connect()
    return jsonify(ok=True)
