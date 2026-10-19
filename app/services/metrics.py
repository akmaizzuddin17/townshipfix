"""The three measures from the proposal, plus trust indicators."""
import statistics

from .. import clock, db


def _median(xs):
    return round(statistics.median(xs), 1) if xs else None


def compute():
    reports = db.q("SELECT merged, client_duration_ms FROM reports")
    tickets = db.q("SELECT * FROM tickets WHERE status != 'merged'")
    staff_merged = db.q1("SELECT COUNT(*) AS n FROM tickets WHERE status='merged'")["n"]
    durations = [r["client_duration_ms"] / 1000 for r in reports if r["client_duration_ms"]]
    closed = [t for t in tickets if t["status"] == "closed"]
    resolution = [clock.hours_between(t["created_at"], t["closed_at"]) for t in closed if t["closed_at"]]
    by_reason = {}
    for t in closed:
        by_reason[t["close_reason"]] = by_reason.get(t["close_reason"], 0) + 1
    evidence_closed = by_reason.get("resident_confirmed", 0) + by_reason.get("auto_after_verified", 0)
    rejected = db.q1("SELECT COUNT(*) AS n FROM events WHERE kind='completion_rejected'")["n"]
    open_t = [t for t in tickets if t["status"] != "closed"]
    now = clock.now()
    overdue = sum(1 for t in open_t if t["sla_due_at"] and now > clock.parse(t["sla_due_at"]))
    bands = {}
    for t in open_t:
        bands[t["priority_band"]] = bands.get(t["priority_band"], 0) + 1
    teams = {}
    for t in open_t:
        teams[t["team"]] = teams.get(t["team"], 0) + 1
    return {
        "reports": len(reports),
        "tickets": len(tickets),
        "duplicates_merged": sum(1 for r in reports if r["merged"]),
        "duplicates_merged_by_staff": staff_merged,
        "median_report_seconds": _median(durations),
        "median_resolution_hours": _median(resolution),
        "closed": len(closed),
        "closed_with_verified_evidence_pct": round(100 * evidence_closed / len(closed)) if closed else None,
        "closed_by_reason": by_reason,
        "fake_or_weak_closures_blocked": rejected,
        "reopened": sum(t["reopen_count"] for t in tickets),
        "open": len(open_t),
        "overdue": overdue,
        "open_by_priority": bands,
        "open_by_team": teams,
    }
