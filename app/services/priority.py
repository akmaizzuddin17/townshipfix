"""Impact-based priority: a transparent score out of 100 with its reasons.

Score = category severity x 10
      + impact flags (wheelchair access, injury, school nearby, ...)
      + more residents affected (number of reporters)
      + waiting time (so low-priority jobs are not ignored forever)
Emergencies (live wires, gas, open manholes...) skip the queue entirely.
"""
import math
from datetime import timedelta

from .. import clock, config


def compute(category, flags, reporters, created_at, urgent, now=None):
    now = now or clock.now()
    cat = config.CATEGORIES.get(category, config.CATEGORIES["other"])
    reasons = [{"points": cat["severity"] * 10, "why": f"{cat['en']}: base severity {cat['severity']}/5"}]
    for f in sorted(set(flags)):
        info = config.IMPACT_FLAGS.get(f)
        if info:
            reasons.append({"points": info["points"], "why": info["en"]})
    if reporters > 1:
        pts = min(15, round(6 * math.log2(reporters)))
        reasons.append({"points": pts, "why": f"{reporters} residents reported this"})
    hours = max(0.0, (now - clock.parse(created_at)).total_seconds() / 3600)
    if hours >= 24:
        pts = min(15, int(hours // 24) * 3)
        reasons.append({"points": pts, "why": f"Waiting {int(hours // 24)} day(s)"})
    score = min(100, sum(r["points"] for r in reasons))
    if urgent:
        band, sla_h = "P0", config.EMERGENCY_SLA_HOURS
        score = 100
        reasons.insert(0, {"points": 0, "why": "Danger to life detected: emergency, security alerted"})
    else:
        band, sla_h = next((b, h) for (m, b, h) in config.PRIORITY_BANDS if score >= m)
    due = clock.parse(created_at) + timedelta(hours=sla_h)
    return {"score": score, "band": band, "reasons": reasons, "sla_due_at": clock.iso(due),
            "sla_hours": sla_h}
