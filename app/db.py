"""SQLite storage. One file, no server, easy to reset for a demo."""
import json
import sqlite3
import threading
from contextlib import contextmanager

from . import config

_local = threading.local()
_generation = 0  # bumped by wipe(); every thread then reconnects to the fresh file

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    category TEXT NOT NULL,
    team TEXT NOT NULL,
    status TEXT NOT NULL,              -- open, assigned, in_progress, awaiting_confirmation, closed, merged
    lat REAL, lng REAL,
    landmark TEXT,
    title TEXT,
    flags TEXT DEFAULT '[]',           -- json list of impact flags (union of reports)
    urgent INTEGER DEFAULT 0,
    urgent_reasons TEXT DEFAULT '[]',
    priority_score INTEGER DEFAULT 0,
    priority_band TEXT DEFAULT 'P3',
    priority_reasons TEXT DEFAULT '[]',
    sla_due_at TEXT,
    assigned_to TEXT,
    possible_dup_of TEXT,
    merged_into TEXT,
    after_photo TEXT,
    verification TEXT,                 -- json result of the last completion check
    close_reason TEXT,                 -- resident_confirmed, auto_after_verified, supervisor_override
    reopen_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    assigned_at TEXT, started_at TEXT, completed_at TEXT, closed_at TEXT
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    token TEXT NOT NULL,               -- secret the resident's phone keeps to confirm/reopen
    text TEXT,
    lang TEXT DEFAULT 'en',
    category_chosen TEXT,
    category_suggested TEXT,
    lat REAL, lng REAL,
    location_source TEXT,              -- photo_gps, device_gps, zone, address_search, map_pin
    location_accuracy_m REAL,
    landmark TEXT,
    photo TEXT,
    privacy TEXT DEFAULT '{}',
    flags TEXT DEFAULT '[]',
    on_behalf_of TEXT,
    contact TEXT,
    client_duration_ms INTEGER,
    merged INTEGER DEFAULT 0,
    merge_explanation TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    kind TEXT NOT NULL,
    detail TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER,
    at TEXT NOT NULL,
    channel TEXT NOT NULL,
    recipient TEXT,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_ticket ON reports(ticket_id);
CREATE INDEX IF NOT EXISTS idx_events_ticket ON events(ticket_id);
"""


def connect():
    conn = getattr(_local, "conn", None)
    if conn is None or getattr(_local, "path", None) != str(config.DB_PATH) or getattr(_local, "gen", -1) != _generation:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        # autocommit mode; multi-step writes use transaction() below
        conn = sqlite3.connect(str(config.DB_PATH), check_same_thread=False, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        # Additive migration: preserve existing reports when upgrading a demo.
        columns = {r[1] for r in conn.execute("PRAGMA table_info(reports)")}
        if "location_accuracy_m" not in columns:
            conn.execute("ALTER TABLE reports ADD COLUMN location_accuracy_m REAL")
        _local.conn, _local.path, _local.gen = conn, str(config.DB_PATH), _generation
    return conn


def wipe():
    """Delete the database (demo reset). Other threads reconnect on their next query."""
    global _generation
    reset_connection()
    _generation += 1
    for suffix in ("", "-wal", "-shm"):
        p = config.DB_PATH.with_name(config.DB_PATH.name + suffix)
        if p.exists():
            p.unlink()


def reset_connection():
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
    _local.conn = None


def row(r):
    if r is None:
        return None
    d = dict(r)
    for k in ("flags", "urgent_reasons", "priority_reasons", "verification", "privacy"):
        if k in d and isinstance(d[k], str) and d[k]:
            try:
                d[k] = json.loads(d[k])
            except ValueError:
                pass
    return d


def q(sql, args=()):
    return [row(r) for r in connect().execute(sql, args).fetchall()]


def q1(sql, args=()):
    return row(connect().execute(sql, args).fetchone())


def ex(sql, args=()):
    return connect().execute(sql, args).lastrowid


@contextmanager
def transaction():
    """All-or-nothing writes that other requests never see half-done.
    BEGIN IMMEDIATE also makes concurrent report submissions queue up, so two
    residents reporting the same problem at the same moment still get one ticket."""
    conn = connect()
    if conn.in_transaction:  # already inside one: just join it
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
