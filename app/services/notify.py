"""Messages to residents and teams.

In this prototype they go to an 'outbox' you can see on the staff dashboard
(simulated SMS / WhatsApp). Swap send() for a real gateway later.
"""
from .. import clock, config, db

TEMPLATES = {
    "received": {
        "en": "TownshipFix: we got your report {code} ({cat}). Expected fix by {due}. Track: {code}",
        "ms": "TownshipFix: laporan {code} ({cat}) diterima. Dijangka siap sebelum {due}. Semak: {code}",
    },
    "merged": {
        "en": "TownshipFix: {n} residents have now reported this problem ({code}). Your report was added; it is now higher priority.",
        "ms": "TownshipFix: {n} penduduk telah melaporkan masalah ini ({code}). Laporan anda ditambah; keutamaan dinaikkan.",
    },
    "assigned": {
        "en": "TownshipFix: {code} is assigned to the {team}.",
        "ms": "TownshipFix: {code} telah diserahkan kepada {team}.",
    },
    "confirm": {
        "en": "TownshipFix: {code} has been repaired. Please check the photo and tap Confirm or Reopen in the app.",
        "ms": "TownshipFix: {code} telah dibaiki. Sila semak gambar dan tekan Sahkan atau Buka Semula dalam aplikasi.",
    },
    "closed": {
        "en": "TownshipFix: {code} is closed. Thank you for helping your neighbourhood.",
        "ms": "TownshipFix: {code} ditutup. Terima kasih kerana membantu kejiranan anda.",
    },
    "reopened": {
        "en": "TownshipFix: {code} was reopened and sent back to the team.",
        "ms": "TownshipFix: {code} dibuka semula dan dihantar kembali kepada pasukan.",
    },
}


def send(ticket_id, channel, recipient, message):
    db.ex("INSERT INTO outbox (ticket_id, at, channel, recipient, message) VALUES (?,?,?,?,?)",
          (ticket_id, clock.iso(clock.now()), channel, recipient, message))


def residents(ticket, kind, **kw):
    """Notify every resident on the ticket in their own language."""
    seen = set()
    for r in db.q("SELECT contact, lang FROM reports WHERE ticket_id=?", (ticket["id"],)):
        to = r["contact"] or "in-app"
        if to in seen:
            continue
        seen.add(to)
        lang = r["lang"] if r["lang"] in ("en", "ms") else "en"
        cat = config.CATEGORIES.get(ticket["category"], config.CATEGORIES["other"])[lang]
        team = config.TEAMS.get(ticket["team"], ticket["team"])
        msg = TEMPLATES[kind][lang].format(code=ticket["code"], cat=cat, team=team, **kw)
        send(ticket["id"], "sms" if r["contact"] else "in-app", to, msg)


def team(ticket, message):
    send(ticket["id"], "team", config.TEAMS.get(ticket["team"], ticket["team"]), message)


def security(ticket, reasons):
    send(ticket["id"], "security", config.TEAMS["security"],
         f"EMERGENCY {ticket['code']} at {ticket['landmark'] or 'reported location'}: "
         f"{', '.join(reasons)}. Please attend now.")
