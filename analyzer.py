"""LLM analysis: label speakers, detect rule breaches R2-R6, judge sentiment. R1 is done in scoring.py."""
import json
import os
import re

from rules import LLM_RULES, RULES
from transcribe import mock_mode

SYSTEM_PROMPT = """You are a compliance auditor for an RBI-registered NBFC (Shaha Finlease) that recovers
personal-loan and credit-card dues by phone. Calls are in Hindi, English, Marathi, Kannada or a mix, written in
Devanagari or Roman script. You get a transcript split into numbered segments. Whisper may merge two speakers in
one segment; label the main speaker.

Tasks:
1. Label every segment as "Agent" (the collections caller) or "Borrower" (anyone else, including a relative or
   colleague who picks up).
2. Give each segment a sentiment: positive, neutral or negative (tone of that speaker).
3. Report breaches of ONLY these rules, by the Agent:
   R2 Abusive or foul language: slurs, swearing, insults ("idiot", "bewakoof", "nalayak"), demeaning the borrower.
   R3 Threats or intimidation: police, jail, arrest, warrant, "we will come to your house", sending people, harm.
   R4 Shaming or disclosure to third parties: telling a relative, colleague, employer or neighbour about the debt,
      calling the borrower a defaulter to others, or threatening to tell them.
   R5 Asking for OTP, PIN, CVV or passwords, in any language.
   R6 Mandatory opening: within the agent's first lines the agent must give their own name, the company name and
      the purpose of the call. Flag if ANY of these three is missing. Quote the agent's first line.
   Do NOT report R1.

Be careful about false alarms. These are NOT breaches: a polite reminder of the amount due, asking for a payment
date, a firm but civil tone, a neutral mention that dues must be paid, or a borrower's own rude words (only the
Agent is audited). Only flag R3 for explicit threats. Flag each breach once, at the segment where it happens.
"quote" must be copied exactly from that segment's text. Use the rule codes exactly as written above.

Also give: borrower_sentiment overall (positive, neutral or negative), agent_stayed_calm (true/false: did the agent
stay calm and professional), language (Hindi, English, Hindi-English, Marathi, Kannada or Mixed), and a one-line summary.

Return ONLY JSON of this shape:
{"segments":[{"id":0,"speaker":"Agent","sentiment":"neutral"}],
 "violations":[{"rule":"R3","segment_id":4,"quote":"...","reason":"short reason"}],
 "borrower_sentiment":"negative","agent_stayed_calm":false,"language":"Hindi-English","summary":"..."}"""


def analyze(segments):
    """segments: list of {start,end,text[,speaker]}. Returns merged segments + violations + call fields."""
    if not segments:
        return {"segments": [], "violations": [], "borrower_sentiment": "neutral",
                "agent_stayed_calm": True, "language": None, "summary": "Empty transcript"}
    data = _mock_analyze(segments) if mock_mode() else _llm_analyze(segments)
    return _clean(data, segments)


def _llm_analyze(segments):
    from openai import OpenAI

    numbered = "\n".join(f"[{i}] ({s['start']:.1f}s) {s['text']}" for i, s in enumerate(segments))
    rules_table = "\n".join(f"{k}: {v[0]} (severity {v[1]})" for k, v in RULES.items() if k in LLM_RULES)
    resp = OpenAI().chat.completions.create(
        model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Rules in force:\n{rules_table}\n\nTranscript:\n{numbered}"},
        ],
    )
    return json.loads(resp.choices[0].message.content)


def _clean(data, segments):
    """Validate the model output so bad JSON never breaks the database."""
    labels = {int(s.get("id", -1)): s for s in data.get("segments", []) if isinstance(s, dict)}
    out_segs = []
    for i, s in enumerate(segments):
        lab = labels.get(i, {})
        speaker = s.get("speaker") or lab.get("speaker")
        sentiment = lab.get("sentiment", "neutral")
        out_segs.append({**s, "idx": i,
                         "speaker": speaker if speaker in ("Agent", "Borrower") else "Agent",
                         "sentiment": sentiment if sentiment in ("positive", "neutral", "negative") else "neutral"})
    seen, violations = set(), []
    for v in data.get("violations", []):
        try:
            code, sid = v["rule"], int(v["segment_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if code not in LLM_RULES or not 0 <= sid < len(segments) or (code, sid) in seen:
            continue
        seen.add((code, sid))
        text = segments[sid]["text"]
        quote = v.get("quote") or text
        violations.append({"rule": code, "segment_id": sid,
                           "quote": quote if quote in text else text,
                           "reason": v.get("reason", ""), "severity": RULES[code][1]})
    bs = data.get("borrower_sentiment")
    return {"segments": out_segs, "violations": violations,
            "borrower_sentiment": bs if bs in ("positive", "neutral", "negative") else "neutral",
            "agent_stayed_calm": bool(data.get("agent_stayed_calm", True)),
            "language": data.get("language"), "summary": data.get("summary", "")}


# ---- Mock analyzer: crude keyword heuristic, ONLY for testing the app without an API ----
_MOCK_PATTERNS = {
    "R2": r"bewakoof|idiot|stupid|fool|badtameez|nalayak|useless idiot|shut up",
    "R3": r"police|jail|arrest|warrant|ghar (bhi )?aayenge|ghar ke bahar|aadmi bhej",
    "R4": r"office mein|sabko pata|padosiyon|defaulter|your manager|whole team",
    "R5": r"\botp\b|\bcvv\b|\bpin\b|password",
}


def _mock_analyze(segments):
    segs, violations = [], []
    for i, s in enumerate(segments):
        neg = bool(re.search(r"harass|useless|galat|dara|complaint|dhamki|leave me alone|stop", s["text"], re.I))
        segs.append({"id": i, "speaker": s.get("speaker", "Agent"), "sentiment": "negative" if neg else "neutral"})
        if s.get("speaker") == "Agent":
            for code, pat in _MOCK_PATTERNS.items():
                if re.search(pat, s["text"], re.I):
                    violations.append({"rule": code, "segment_id": i, "quote": s["text"], "reason": "keyword match (mock)"})
    first_agent = next((s["text"] for s in segments if s.get("speaker") == "Agent"), "")
    if not re.search(r"shaha", first_agent, re.I):
        violations.append({"rule": "R6", "segment_id": 0, "quote": first_agent, "reason": "company not stated (mock)"})
    borrower_neg = sum(1 for x, s in zip(segs, segments) if s.get("speaker") == "Borrower" and x["sentiment"] == "negative")
    return {"segments": segs, "violations": violations,
            "borrower_sentiment": "negative" if borrower_neg >= 2 else "neutral",
            "agent_stayed_calm": not any(v["rule"] in ("R2", "R3", "R4") for v in violations),
            "language": "Mixed", "summary": "Mock analysis (keyword heuristic)"}
