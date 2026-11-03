"""Speech to text through a hosted API (OpenAI Whisper). MOCK_MODE uses the call scripts instead."""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT_FILES = [
    ROOT / "data/reference/call_scripts_01_to_05.md",
    ROOT / "data/reference/call_scripts_06_to_20.md",
]


def mock_mode():
    return os.environ.get("MOCK_MODE", "0") == "1"


def _get(obj, key):
    return obj[key] if isinstance(obj, dict) else getattr(obj, key)


def transcribe(call_id, audio_path):
    """Return (segments, duration_seconds). Each segment: {start, end, text[, speaker]}."""
    if mock_mode():
        return _mock_transcribe(call_id)

    from openai import OpenAI

    if not audio_path or not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file missing for {call_id}: {audio_path}")
    client = OpenAI()
    with open(audio_path, "rb") as f:
        r = client.audio.transcriptions.create(
            model=os.environ.get("STT_MODEL", "whisper-1"),
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
            # A hint helps with mixed Hindi and English phone speech.
            prompt="Debt collection phone call between an agent and a borrower. "
                   "Hindi and English mixed. Company: Shaha Finlease.",
        )
    segs = [
        {"start": float(_get(s, "start")), "end": float(_get(s, "end")),
         "text": _get(s, "text").strip()}
        for s in _get(r, "segments")
    ]
    duration = float(_get(r, "duration")) if _get(r, "duration") else (segs[-1]["end"] if segs else 0)
    return segs, duration


def _mock_transcribe(call_id):
    """Fake transcript from the written scripts, ~5 seconds per line. UI testing only."""
    text = "\n".join(p.read_text(encoding="utf-8") for p in SCRIPT_FILES if p.exists())
    block = re.search(rf"## {call_id}\b.*?(?=\n## call_|\Z)", text, re.S)
    segs, t = [], 0.0
    if block:
        for m in re.finditer(r"\*\*(Agent|Borrower)[^*]*:\*\*\s*(.+)", block.group(0)):
            segs.append({"start": t, "end": t + 4.5, "text": m.group(2).strip(), "speaker": m.group(1)})
            t += 5.0
    return segs, t
