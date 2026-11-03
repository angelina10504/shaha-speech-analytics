# Shaha Finlease: Speech Analytics & Compliance (prototype)

Transcribes recorded collection calls, labels each line Agent or Borrower, detects six compliance breaches
with an LLM (plus a plain-code calling-hours check), scores every call 0 to 100, and lets a manager mark each
flag Confirmed or False alarm. A role switcher (Caller, Manager, Head of Collections) filters the data. No login.

## Setup

1. Python 3.10 or newer.
2. Put your key in `.env` (copy `.env.example`): `OPENAI_API_KEY=...`. Keys are never committed.
3. Run `./run.sh`. It creates a venv, installs requirements, seeds the demo data and opens the app.
   Reset the demo at any time with `./run.sh --reset` (or `python seed.py`).

Without an API key you can click through every screen with `MOCK_MODE=1` (fake transcripts from the written
scripts, keyword-based flags). Mock numbers are meaningless and must never be reported as accuracy.

## Demo flow

1. **Upload** (as Manager or Head): upload the 20 `.wav` files from `data/calls/` plus `data/metadata.csv`,
   or press "Load the sample batch". Each call is transcribed, analysed and scored.
2. **Call list**: pick a call, open it.
3. **Call review**: audio player beside the transcript; click a flag (or any timestamp) to play from that moment.
   Managers press Confirm or False alarm with a comment, and the score updates.
4. **Dashboard**: breaches by rule, office and caller, top 5 riskiest callers, precision and recall per rule.
5. Switch to **Caller** to show they only see their own calls; Manager sees their team; Head sees all offices.

## How it works

| Step | File | Notes |
|---|---|---|
| Transcribe | `transcribe.py` | Hosted OpenAI Whisper API, segment timestamps |
| Speakers, rules R2 to R6, sentiment | `analyzer.py` | One LLM call per call: rule table in the prompt, JSON back, output validated |
| R1 calling hours | `scoring.py` | Plain code from the start time in the metadata (08:00 to before 19:00) |
| Score | `scoring.py` | 100 minus 30 (Critical), 20 (High), 10 (Medium), 5 (Low) per active flag; false alarms are not counted |
| Data | `db.py`, `seed.py` | SQLite: Office, User, Call, TranscriptSegment (`segment`), Rule, Violation, Review |
| Screens | `app.py` | Streamlit |
| Accuracy | `accuracy.py`, `evaluate.py` | Precision/recall vs `data/labels.csv`; word error rate vs hand-typed transcripts |

Seed: 3 offices, 60 callers, 7 managers, 1 head, 2,000 metadata-only call records. Those records can only carry the
R1 check until a recording is uploaded, so the dashboard defaults to analysed calls only.

## Test set

`data/labels.csv` labels the 20 calls by hand. Every rule appears at least twice (R1: 2, R2: 3, R3: 4, R4: 3,
R5: 3, R6: 3) and 7 calls are clean. Scripts are in `data/reference/`. The recordings are made by two people
role-playing each script on a phone or laptop microphone (no text-to-speech).

## Accuracy (fill in after running on the real recordings)

Run `python evaluate.py` after processing all 20 calls and paste the output here.

| Rule | Precision | Recall |
|---|---|---|
| R1 | | |
| R2 | | |
| R3 | | |
| R4 | | |
| R5 | | |
| R6 | | |

Word error rate on 3 hand-typed transcripts: _fill in_

## Assumptions and known limits

- Calls are checked from the time they **start**; 19:00 sharp counts as outside the window.
- Only the Agent is audited. A borrower's rude words are not flagged.
- R6 requires name, company and purpose in the agent's opening lines; a missing item flags the call once.
- Speaker labels come from the LLM per Whisper segment. When two speakers share one segment (fast turn-taking)
  the main speaker is used, so a few labels can be wrong.
- Whisper writes Hindi in Devanagari, so quotes in flags appear in that script.
- Flags for a call are replaced if the call is processed again, which also clears its reviews.
- Review permissions are by view only (no login): any Manager view can review the flags it can see.
- Not built (bonus): live streaming, raised-voice detection from audio, real login.
