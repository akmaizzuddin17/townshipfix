"""Single source of 'now' so tests can move time forward."""
from datetime import datetime, timezone

_override = None


def now() -> datetime:
    return _override or datetime.now(timezone.utc)


def set_now(dt):
    """Tests only: freeze time at dt (aware datetime) or None to unfreeze."""
    global _override
    _override = dt


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def hours_between(a: str, b: str) -> float:
    return (parse(b) - parse(a)).total_seconds() / 3600.0
