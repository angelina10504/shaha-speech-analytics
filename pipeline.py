"""Ingest a call (metadata + audio) and run transcribe -> analyse -> score."""
from pathlib import Path

import pandas as pd

from analyzer import analyze
from db import ROOT
from rules import RULES
from scoring import check_r1, parse_time, recompute_score
from transcribe import mock_mode, transcribe

CALLS_DIR = ROOT / "data" / "calls"
REQUIRED_COLUMNS = ["call_id", "caller", "office", "start_time"]


def _ensure_caller(c, name, office_name):
    office = c.execute("SELECT id FROM office WHERE name = ?", (office_name,)).fetchone()
    if office is None:
        office_id = c.execute("INSERT INTO office (name) VALUES (?)", (office_name,)).lastrowid
    else:
        office_id = office["id"]
    row = c.execute("SELECT id FROM user WHERE name = ? AND role = 'caller'", (name,)).fetchone()
    if row:
        return row["id"]
    mgr = c.execute("SELECT id FROM user WHERE role = 'manager' AND office_id = ? ORDER BY id LIMIT 1",
                    (office_id,)).fetchone()
    return c.execute("INSERT INTO user (name, role, office_id, manager_id) VALUES (?, 'caller', ?, ?)",
                     (name, office_id, mgr["id"] if mgr else None)).lastrowid


def ingest_call(c, row, audio_bytes=None):
    """Create or replace one call record from a metadata row (and save its audio file)."""
    call_id = str(row["call_id"]).strip()
    start = parse_time(row["start_time"]).strftime("%Y-%m-%d %H:%M:%S")
    caller_id = _ensure_caller(c, str(row["caller"]).strip(), str(row["office"]).strip())
    audio_path = None
    if audio_bytes:
        CALLS_DIR.mkdir(parents=True, exist_ok=True)
        fname = Path(str(row.get("filename") or f"{call_id}.wav")).name
        audio_path = str(CALLS_DIR / fname)
        Path(audio_path).write_bytes(audio_bytes)
    c.execute("DELETE FROM call WHERE id = ?", (call_id,))
    c.execute("""INSERT INTO call (id, caller_id, account, start_time, status, audio_path)
                 VALUES (?, ?, ?, ?, 'uploaded', ?)""",
              (call_id, caller_id, f"ACC-{call_id}", start, audio_path))
    c.commit()
    return call_id


def process_call(c, call_id):
    """Transcribe, analyse, store segments and flags, and score the call."""
    call = c.execute("SELECT * FROM call WHERE id = ?", (call_id,)).fetchone()
    segments, duration = transcribe(call_id, call["audio_path"])
    result = analyze(segments)

    c.execute("DELETE FROM violation WHERE call_id = ?", (call_id,))
    c.execute("DELETE FROM segment WHERE call_id = ?", (call_id,))
    seg_ids = []
    for s in result["segments"]:
        seg_ids.append(c.execute(
            "INSERT INTO segment (call_id, idx, speaker, start, end, text, sentiment) VALUES (?,?,?,?,?,?,?)",
            (call_id, s["idx"], s["speaker"], s["start"], s["end"], s["text"], s["sentiment"])).lastrowid)

    r1 = check_r1(call["start_time"])
    if r1:
        c.execute("INSERT INTO violation (call_id, rule_code, start, quote, reason, severity) VALUES (?,?,?,?,?,?)",
                  (call_id, "R1", 0, r1["quote"], r1["reason"], r1["severity"]))
    for v in result["violations"]:
        seg = result["segments"][v["segment_id"]]
        c.execute("""INSERT INTO violation (call_id, rule_code, segment_id, start, quote, reason, severity)
                     VALUES (?,?,?,?,?,?,?)""",
                  (call_id, v["rule"], seg_ids[v["segment_id"]], seg["start"], v["quote"], v["reason"], v["severity"]))

    c.execute("""UPDATE call SET duration=?, language=?, status='processed', borrower_sentiment=?,
                 agent_calm=?, summary=? WHERE id=?""",
              (int(duration), result["language"], result["borrower_sentiment"],
               int(result["agent_stayed_calm"]), result["summary"], call_id))
    score = recompute_score(c, call_id)
    c.commit()
    return score


def load_metadata_csv(file_or_path):
    df = pd.read_csv(file_or_path, dtype=str).fillna("")
    df.columns = [x.strip().lower() for x in df.columns]
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Metadata CSV is missing columns: {', '.join(missing)}")
    return df


def ingest_batch(c, metadata_df, audio_files, progress=None):
    """audio_files: {filename: bytes}. Returns a list of (call_id, ok, message)."""
    results = []
    total = len(metadata_df)
    for n, (_, row) in enumerate(metadata_df.iterrows(), 1):
        call_id = str(row["call_id"]).strip()
        fname = Path(str(row.get("filename") or f"{call_id}.wav")).name
        try:
            audio = audio_files.get(fname)
            if audio is None and not mock_mode():
                raise FileNotFoundError(f"audio file '{fname}' was not uploaded")
            ingest_call(c, row.to_dict(), audio)
            score = process_call(c, call_id)
            results.append((call_id, True, f"score {score}"))
        except Exception as e:  # keep the batch going; report the failure per call
            c.rollback()
            results.append((call_id, False, f"{type(e).__name__}: {e}"))
        if progress:
            progress(n / total, f"{call_id} ({n}/{total})")
    return results


def review_flag(c, violation_id, decision, reviewer_id, comment):
    """Manager marks a flag Confirmed or False alarm; the call score updates."""
    call_id = c.execute("SELECT call_id FROM violation WHERE id = ?", (violation_id,)).fetchone()["call_id"]
    c.execute("""INSERT INTO review (violation_id, decision, reviewer_id, comment) VALUES (?,?,?,?)
                 ON CONFLICT(violation_id) DO UPDATE SET decision=excluded.decision,
                 reviewer_id=excluded.reviewer_id, comment=excluded.comment, created_at=CURRENT_TIMESTAMP""",
              (violation_id, decision, reviewer_id, comment))
    score = recompute_score(c, call_id)
    c.commit()
    return score


def rule_name(code):
    return RULES[code][0]
