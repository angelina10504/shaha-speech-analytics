# Shaha Finlease: Speech Analytics & Compliance (prototype)

A prototype that transcribes recorded collection calls, labels each line Agent or Borrower, detects six
compliance breaches (R1 to R6) and borrower sentiment, scores every call 0 to 100, and lets a manager mark
each flag Confirmed or False alarm. A Caller / Manager / Head of Collections switcher filters the data. No login.

## What is built

- **Data model (SQLite):** Office, User, Call, TranscriptSegment (`segment`), Rule, Violation, Review.
- **Seed script:** 3 offices, 60 callers, 7 managers, 1 head and 2,000 call records. Reset with one command (`python seed.py`).
- **Upload screen:** audio files plus a metadata CSV (`call_id, caller, office, start_time`), with progress and per-call errors.
- **Transcription:** hosted Whisper API with segment timestamps.
- **Rule detection:** one LLM call per call returns JSON with speaker labels, sentiment, and breaches R2 to R6 (rule, quote, timestamp, severity). R1 (calling hours) is a plain-code check on the call start time.
- **Scoring:** 100 minus 30 (Critical), 20 (High), 10 (Medium) or 5 (Low) per active flag. False alarms are not counted.
- **Call list and Call review:** audio player beside the transcript; clicking a flag or any timestamp plays from that moment. Managers press Confirm or False alarm with a comment and the score updates.
- **Dashboard:** breaches by rule, office and caller, top 5 riskiest callers, and precision and recall per rule against the hand labels.
- **Role views:** Caller sees their own calls, Manager sees their team, Head sees all offices.
- **Test set material:** scripts for 20 calls (`data/reference/`), hand labels in `data/labels.csv` (every rule appears at least twice, 7 clean calls), and the metadata in `data/metadata.csv`.
- **Evaluation code:** `evaluate.py` prints precision and recall per rule and word error rate against hand-typed transcripts.
- **Mock mode:** `MOCK_MODE=1` runs every screen without an API key, using the written scripts as fake transcripts. Mock results are for testing the screens only.

## Setup

1. Python 3.10 or newer.
2. Copy `.env.example` to `.env` and set `OPENAI_API_KEY`.
3. Run `./run.sh`. It creates a venv, installs requirements, seeds the demo data and starts the app.
   Reset the demo with `./run.sh --reset` (or `python seed.py`).

## Using the app

1. **Upload** (as Manager or Head): upload call recordings (`.wav` or `.mp3`) and a metadata CSV like `data/metadata.csv`.
2. **Call list**: select a call and open it.
3. **Call review**: play audio, click a flag to jump to that moment, and confirm or reject each flag.
4. **Dashboard**: see breaches by rule, office and caller, the riskiest callers and the accuracy table.
5. Switch the view to Caller, Manager or Head to see the filtering.

## Files

| Purpose | File |
|---|---|
| Screens | `app.py` |
| Transcription | `transcribe.py` |
| Speakers, rules R2 to R6, sentiment | `analyzer.py` |
| R1 check and scoring | `scoring.py` |
| Ingest and review logic | `pipeline.py` |
| Schema | `db.py` |
| Demo data | `seed.py` |
| Precision and recall | `accuracy.py`, `evaluate.py` |

## Assumptions

- Calls are checked from the time they start; 19:00 sharp counts as outside the window.
- Only the Agent is audited. A borrower's rude words are not flagged.
- R6 requires name, company and purpose in the agent's opening lines; a missing item flags the call once.
- Speaker labels come from the LLM per Whisper segment. When two speakers share one segment, the main speaker is used.
- Whisper writes Hindi in Devanagari, so quotes in flags appear in that script.
- Processing a call again replaces its flags, which also clears its reviews.
- Review permissions are by view only (no login): any Manager view can review the flags it can see.
- The 2,000 seeded records are metadata only, so only R1 can be checked on them; the dashboard defaults to analysed calls.
