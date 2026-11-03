"""Compliance score: 100 minus a penalty per active flag. False alarms don't count."""
from datetime import datetime

from rules import CALL_END_HOUR, CALL_START_HOUR, PENALTY, RULES


def parse_time(value):
    """Accept 'YYYY-MM-DD HH:MM[:SS]' or ISO strings and return a datetime."""
    value = str(value).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError(f"Unrecognised start_time: {value!r} (use YYYY-MM-DD HH:MM)")


def check_r1(start_time):
    """R1 is a plain metadata check, no LLM. Returns a violation dict or None."""
    dt = parse_time(start_time)
    if dt.hour < CALL_START_HOUR or dt.hour >= CALL_END_HOUR:
        return {
            "rule": "R1",
            "quote": f"Call started at {dt.strftime('%I:%M %p').lstrip('0')}",
            "reason": "Call started outside the allowed 8 AM to 7 PM window",
            "severity": RULES["R1"][1],
        }
    return None


def recompute_score(c, call_id):
    rows = c.execute(
        """SELECT v.severity, r.decision FROM violation v
           LEFT JOIN review r ON r.violation_id = v.id WHERE v.call_id = ?""",
        (call_id,),
    ).fetchall()
    penalty = sum(PENALTY[r["severity"]] for r in rows if r["decision"] != "false_alarm")
    score = max(0, 100 - penalty)
    c.execute("UPDATE call SET score = ? WHERE id = ?", (score, call_id))
    return score
