"""SQLite schema and connection helper."""
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = os.environ.get("DB_PATH", str(ROOT / "shaha.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS office (
    id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);

CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('caller','manager','head')),
    office_id INTEGER REFERENCES office(id),
    manager_id INTEGER REFERENCES user(id));

CREATE TABLE IF NOT EXISTS call (
    id TEXT PRIMARY KEY,
    caller_id INTEGER NOT NULL REFERENCES user(id),
    account TEXT, start_time TEXT NOT NULL, duration INTEGER, language TEXT,
    score INTEGER, status TEXT NOT NULL DEFAULT 'metadata_only',
    audio_path TEXT, borrower_sentiment TEXT, agent_calm INTEGER, summary TEXT);

CREATE TABLE IF NOT EXISTS segment (
    id INTEGER PRIMARY KEY,
    call_id TEXT NOT NULL REFERENCES call(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL, speaker TEXT, start REAL, end REAL,
    text TEXT, sentiment TEXT);

CREATE TABLE IF NOT EXISTS rule (
    code TEXT PRIMARY KEY, name TEXT NOT NULL, severity TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS violation (
    id INTEGER PRIMARY KEY,
    call_id TEXT NOT NULL REFERENCES call(id) ON DELETE CASCADE,
    rule_code TEXT NOT NULL REFERENCES rule(code),
    segment_id INTEGER REFERENCES segment(id) ON DELETE SET NULL,
    start REAL DEFAULT 0, quote TEXT, reason TEXT, severity TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS review (
    id INTEGER PRIMARY KEY,
    violation_id INTEGER NOT NULL UNIQUE REFERENCES violation(id) ON DELETE CASCADE,
    decision TEXT NOT NULL CHECK (decision IN ('confirmed','false_alarm')),
    reviewer_id INTEGER REFERENCES user(id), comment TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""


def connect():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def init_db(reset=False):
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    c = connect()
    c.executescript(SCHEMA)
    c.commit()
    return c
