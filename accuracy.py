"""Precision and recall per rule against the hand-labelled calls (data/labels.csv)."""
import csv

from db import ROOT
from rules import RULES

LABELS_PATH = ROOT / "data" / "labels.csv"


def load_labels(path=LABELS_PATH):
    with open(path, newline="", encoding="utf-8") as f:
        return {r["call_id"]: {x for x in r["breaches"].split(";") if x} for r in csv.DictReader(f)}


def compute(c, labels=None):
    """Compare raw system flags (before any manager review) with the hand labels.
    Only labelled calls that have been processed are counted."""
    labels = labels or load_labels()
    rows = c.execute("SELECT id FROM call WHERE status = 'processed'").fetchall()
    ids = [r["id"] for r in rows if r["id"] in labels]
    predicted = {i: set() for i in ids}
    for v in c.execute("SELECT call_id, rule_code FROM violation").fetchall():
        if v["call_id"] in predicted:
            predicted[v["call_id"]].add(v["rule_code"])
    table = []
    for code in RULES:
        tp = sum(1 for i in ids if code in labels[i] and code in predicted[i])
        fp = sum(1 for i in ids if code not in labels[i] and code in predicted[i])
        fn = sum(1 for i in ids if code in labels[i] and code not in predicted[i])
        table.append({"rule": code, "labelled": tp + fn, "TP": tp, "FP": fp, "FN": fn,
                      "precision": round(tp / (tp + fp), 2) if tp + fp else None,
                      "recall": round(tp / (tp + fn), 2) if tp + fn else None})
    clean = [i for i in ids if not labels[i]]
    false_alarm_calls = [i for i in clean if predicted[i]]
    return {"table": table, "n_calls": len(ids), "clean_calls": len(clean),
            "clean_calls_wrongly_flagged": len(false_alarm_calls)}
