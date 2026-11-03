"""Print accuracy numbers:  python evaluate.py

1. Precision/recall per rule on the labelled calls already processed in the app.
2. Word error rate on hand-typed transcripts in data/reference/wer/<call_id>.txt (if present)."""
import re
import sys

from accuracy import compute
from db import ROOT, connect
from transcribe import mock_mode

WER_DIR = ROOT / "data" / "reference" / "wer"


def _normalise(text):
    return re.sub(r"[^\w\s]", " ", text.lower()).split()


def wer_report(c):
    import jiwer

    out = []
    for ref_file in sorted(WER_DIR.glob("call_*.txt")):
        call_id = ref_file.stem
        segs = c.execute("SELECT text FROM segment WHERE call_id = ? ORDER BY idx", (call_id,)).fetchall()
        if not segs:
            out.append((call_id, None))
            continue
        ref = " ".join(_normalise(ref_file.read_text(encoding="utf-8")))
        hyp = " ".join(_normalise(" ".join(s["text"] for s in segs)))
        out.append((call_id, jiwer.wer(ref, hyp)))
    return out


def main():
    c = connect()
    if mock_mode():
        print("*** MOCK_MODE is on: these numbers are NOT real and must not be reported. ***\n")
    acc = compute(c)
    print(f"Labelled calls processed: {acc['n_calls']}  (clean: {acc['clean_calls']}, "
          f"clean calls wrongly flagged: {acc['clean_calls_wrongly_flagged']})\n")
    print(f"{'rule':<5}{'labelled':>9}{'TP':>4}{'FP':>4}{'FN':>4}{'precision':>11}{'recall':>8}")
    for r in acc["table"]:
        p = "n/a" if r["precision"] is None else f"{r['precision']:.2f}"
        rc = "n/a" if r["recall"] is None else f"{r['recall']:.2f}"
        print(f"{r['rule']:<5}{r['labelled']:>9}{r['TP']:>4}{r['FP']:>4}{r['FN']:>4}{p:>11}{rc:>8}")
    print("\nWord error rate (hand-typed references):")
    refs = wer_report(c) if WER_DIR.exists() else []
    if not refs:
        print(f"  none found. Put 3 files like {WER_DIR}/call_05.txt there (see README in that folder).")
    for call_id, w in refs:
        print(f"  {call_id}: " + ("call not processed yet" if w is None else f"{w:.1%}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
