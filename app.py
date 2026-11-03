"""Shaha Finlease speech analytics and compliance prototype (Streamlit).

Run:  streamlit run app.py
Screens: Upload, Call list, Call review, Dashboard. A role switcher at the top filters the data."""
import os
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import seed
from accuracy import compute
from db import DB_PATH, ROOT, connect
from pipeline import ingest_batch, load_metadata_csv, review_flag
from rules import PENALTY, RULES
from transcribe import mock_mode

st.set_page_config(page_title="Shaha Finlease - Speech Analytics", layout="wide")

ROLES = ["Caller", "Manager", "Head of Collections"]
PAGES = ["Upload", "Call list", "Call review", "Dashboard"]
SENTIMENT_ICON = {"positive": "🙂", "neutral": "😐", "negative": "😠"}

if not Path(DB_PATH).exists():
    seed.main()


# ---------- helpers ----------
def fmt(sec):
    sec = int(sec or 0)
    return f"{sec // 60:02d}:{sec % 60:02d}"


def scope(role, me_id):
    """SQL filter that decides which calls a role may see."""
    if role == "Caller":
        return "c.caller_id = ?", (me_id,)
    if role == "Manager":
        return "u.manager_id = ?", (me_id,)
    return "1 = 1", ()


def calls_df(c, where, params):
    q = f"""
    SELECT c.id, u.name AS caller, o.name AS office, c.start_time, c.language, c.status, c.score,
      (SELECT COUNT(*) FROM violation v LEFT JOIN review r ON r.violation_id = v.id
         WHERE v.call_id = c.id AND COALESCE(r.decision, '') != 'false_alarm') AS flags,
      (SELECT COUNT(*) FROM violation v LEFT JOIN review r ON r.violation_id = v.id
         WHERE v.call_id = c.id AND r.id IS NULL) AS pending
    FROM call c JOIN user u ON u.id = c.caller_id JOIN office o ON o.id = u.office_id
    WHERE {where}
    ORDER BY (c.status = 'processed') DESC, c.start_time DESC"""
    return pd.read_sql_query(q, c, params=params)


def open_call(call_id):
    st.session_state.open_call = call_id
    st.session_state.nav = "Call review"


def play_from(call_id, seconds):
    st.session_state[f"play_{call_id}"] = int(seconds)
    st.session_state.autoplay = True


def decide(violation_id, decision, reviewer_id):
    conn = connect()
    try:
        review_flag(conn, violation_id, decision, reviewer_id, st.session_state.get(f"cm_{violation_id}", ""))
    finally:
        conn.close()


# ---------- screens ----------
def page_upload(c, role):
    st.subheader("Upload call recordings")
    if role == "Caller":
        st.info("Only managers and the Head of Collections can upload batches. Switch the view above.")
        return
    st.write("Upload audio files (WAV or MP3) together with a metadata CSV with columns "
             "`call_id, caller, office, start_time` (and optionally `filename`).")
    audio = st.file_uploader("Audio files", type=["wav", "mp3"], accept_multiple_files=True)
    meta = st.file_uploader("Metadata CSV", type=["csv"])
    col1, col2 = st.columns(2)
    run = col1.button("Process uploaded batch", type="primary", disabled=not (meta and (audio or mock_mode())))
    sample = col2.button("Load the sample batch from data/ (metadata.csv + data/calls)")
    if not (run or sample):
        return
    try:
        if run:
            df = load_metadata_csv(meta)
            files = {f.name: f.getvalue() for f in audio}
        else:
            df = load_metadata_csv(ROOT / "data" / "metadata.csv")
            files = {p.name: p.read_bytes() for p in (ROOT / "data" / "calls").glob("*") if p.suffix.lower() in (".wav", ".mp3")}
    except Exception as e:
        st.error(f"Could not read the batch: {e}")
        return
    bar = st.progress(0.0, text="Starting")
    results = ingest_batch(c, df, files, progress=lambda f, t: bar.progress(f, text=t))
    bar.empty()
    ok = sum(1 for r in results if r[1])
    st.success(f"{ok} of {len(results)} calls processed.")
    out = pd.DataFrame(results, columns=["call_id", "ok", "result"])
    st.dataframe(out, hide_index=True)
    if ok < len(results):
        st.warning("Some calls failed. The messages above say why; fix the file and upload again.")


def page_list(c, role, me_id):
    st.subheader("Call list")
    where, params = scope(role, me_id)
    df = calls_df(c, where, params)
    only = st.checkbox("Only calls with an analysed recording", value=True)
    if only:
        df = df[df.status == "processed"].reset_index(drop=True)
    if df.empty:
        st.info("No calls to show for this view yet. Upload a batch first (Upload screen).")
        return
    st.caption(f"{len(df)} calls. Select a row, then open it.")
    event = st.dataframe(df, hide_index=True, on_select="rerun", selection_mode="single-row")
    rows = event.selection.rows
    if rows:
        cid = df.iloc[rows[0]]["id"]
        st.button(f"Open review for {cid}", type="primary", on_click=open_call, args=(cid,))


def page_review(c, role, me_id):
    st.subheader("Call review")
    where, params = scope(role, me_id)
    df = calls_df(c, where, params)
    df = df[df.status == "processed"]
    if df.empty:
        st.info("No analysed calls for this view yet.")
        return
    ids = list(df.id)
    default = st.session_state.get("open_call")
    call_id = st.selectbox("Call", ids, index=ids.index(default) if default in ids else 0)
    st.session_state.open_call = call_id

    call = c.execute("""SELECT c.*, u.name AS caller, o.name AS office FROM call c
                        JOIN user u ON u.id = c.caller_id JOIN office o ON o.id = u.office_id
                        WHERE c.id = ?""", (call_id,)).fetchone()
    segs = c.execute("SELECT * FROM segment WHERE call_id = ? ORDER BY idx", (call_id,)).fetchall()
    flags = c.execute("""SELECT v.*, r.decision, r.comment FROM violation v
                         LEFT JOIN review r ON r.violation_id = v.id
                         WHERE v.call_id = ? ORDER BY v.start, v.id""", (call_id,)).fetchall()
    flag_codes = {}
    for f in flags:
        if f["segment_id"] and f["decision"] != "false_alarm":
            flag_codes.setdefault(f["segment_id"], []).append(f["rule_code"])

    left, right = st.columns([3, 2])
    with left:
        audio_path = call["audio_path"]
        if audio_path and os.path.exists(audio_path):
            st.audio(audio_path, start_time=st.session_state.get(f"play_{call_id}", 0),
                     autoplay=st.session_state.get("autoplay", False))
            st.session_state.autoplay = False
        else:
            st.caption("No audio file for this call (expected in mock mode only).")
        st.markdown("**Transcript** (click a time to play from there)")
        for s in segs:
            a, b = st.columns([1, 9])
            a.button(f"▶ {fmt(s['start'])}", key=f"seg_{s['id']}", on_click=play_from, args=(call_id, s["start"]))
            icon = SENTIMENT_ICON.get(s["sentiment"], "")
            line = f"**{s['speaker']}** {icon}: {s['text']}"
            if s["id"] in flag_codes:
                b.error(f"{line}  \n`{' '.join(flag_codes[s['id']])}`")
            else:
                b.markdown(line)

    with right:
        st.markdown("**Scorecard**")
        m1, m2 = st.columns(2)
        m1.metric("Compliance score", f"{call['score']}/100")
        m2.metric("Active flags", sum(1 for f in flags if f["decision"] != "false_alarm"))
        st.write(f"Caller: **{call['caller']}** ({call['office']})  \nStarted: {call['start_time']}  \n"
                 f"Language: {call['language'] or 'n/a'}  \nDuration: {fmt(call['duration'])}")
        st.write(f"Borrower sentiment: **{SENTIMENT_ICON.get(call['borrower_sentiment'], '')} {call['borrower_sentiment']}**  \n"
                 f"Agent stayed calm: **{'yes' if call['agent_calm'] else 'no'}**")
        if call["summary"]:
            st.caption(call["summary"])

        st.markdown("**Flags**")
        if not flags:
            st.success("No breaches detected.")
        can_review = role in ("Manager", "Head of Collections")
        if flags and not can_review:
            st.caption("Callers can see flags but only managers can review them.")
        for f in flags:
            with st.container(border=True):
                name, _ = RULES[f["rule_code"]]
                st.markdown(f"**{f['rule_code']}: {name}**  \nSeverity: **{f['severity']}**" +
                            (f" · at {fmt(f['start'])}" if f["segment_id"] else " · from call metadata"))
                st.markdown(f"> {f['quote']}")
                if f["reason"]:
                    st.caption(f["reason"])
                if f["segment_id"]:
                    st.button("▶ Play this moment", key=f"pl_{f['id']}", on_click=play_from, args=(call_id, f["start"]))
                if f["decision"]:
                    st.write("Review: " + ("✅ Confirmed" if f["decision"] == "confirmed" else "❎ False alarm")
                             + (f" - {f['comment']}" if f["comment"] else ""))
                if can_review:
                    key = f"cm_{f['id']}"
                    if key not in st.session_state:
                        st.session_state[key] = f["comment"] or ""
                    st.text_input("Comment", key=key)
                    b1, b2 = st.columns(2)
                    b1.button("Confirm", key=f"cf_{f['id']}", on_click=decide, args=(f["id"], "confirmed", me_id))
                    b2.button("False alarm", key=f"fa_{f['id']}", on_click=decide, args=(f["id"], "false_alarm", me_id))


def page_dashboard(c, role, me_id):
    st.subheader("Dashboard")
    where, params = scope(role, me_id)
    analysed_only = st.checkbox("Only analysed calls (with a recording)", value=True,
                                help="Off: also counts the ~2,000 metadata-only records, where only R1 can be checked.")
    status_sql = " AND c.status = 'processed'" if analysed_only else ""
    flags = pd.read_sql_query(f"""
        SELECT v.id, v.rule_code, v.severity, u.name AS caller, o.name AS office,
               COALESCE(r.decision, 'pending') AS decision
        FROM violation v JOIN call c ON c.id = v.call_id JOIN user u ON u.id = c.caller_id
        JOIN office o ON o.id = u.office_id LEFT JOIN review r ON r.violation_id = v.id
        WHERE {where}{status_sql}""", c, params=params)
    flags = flags[flags.decision != "false_alarm"]
    calls = pd.read_sql_query(f"""
        SELECT c.id, c.score, u.name AS caller, o.name AS office FROM call c JOIN user u ON u.id = c.caller_id
        JOIN office o ON o.id = u.office_id WHERE {where}{status_sql}""", c, params=params)

    k1, k2, k3 = st.columns(3)
    k1.metric("Calls", len(calls))
    k2.metric("Active flags", len(flags))
    k3.metric("Average score", "n/a" if calls.score.dropna().empty else round(calls.score.mean(), 1))
    if flags.empty:
        st.info("No flags for this view yet.")
    else:
        g1, g2, g3 = st.columns(3)
        g1.markdown("**Breaches by rule**")
        g1.bar_chart(flags.rule_code.value_counts().reindex(list(RULES), fill_value=0))
        g2.markdown("**Breaches by office**")
        g2.bar_chart(flags.office.value_counts())
        g3.markdown("**Breaches by caller (top 10)**")
        g3.bar_chart(flags.caller.value_counts().head(10))

        st.markdown("**Top 5 riskiest callers** (risk points: Critical 30, High 20, Medium 10, Low 5)")
        flags = flags.assign(points=flags.severity.map(PENALTY))
        risk = flags.groupby(["caller", "office"]).agg(
            active_flags=("id", "count"), critical=("severity", lambda s: (s == "Critical").sum()),
            risk_points=("points", "sum")).reset_index()
        avg = calls.groupby("caller").score.mean().round(1).rename("avg_score")
        risk = risk.merge(avg, on="caller", how="left").sort_values(
            ["risk_points", "critical"], ascending=False).head(5)
        st.dataframe(risk, hide_index=True)

    st.markdown("**Accuracy on the 20 hand-labelled calls** (system flags before any manager review)")
    if mock_mode():
        st.warning("MOCK_MODE is on: these numbers come from a keyword heuristic and are not real results.")
    acc = compute(c)
    if acc["n_calls"] == 0:
        st.info("Upload and process the labelled calls (call_01 to call_20) to see precision and recall.")
    else:
        st.dataframe(pd.DataFrame(acc["table"]), hide_index=True)
        st.caption(f"{acc['n_calls']} labelled calls processed, {acc['clean_calls']} clean; "
                   f"{acc['clean_calls_wrongly_flagged']} clean calls wrongly flagged. Word error rate: run `python evaluate.py`.")


# ---------- main ----------
def main():
    st.title("Shaha Finlease: Speech Analytics & Compliance")
    if mock_mode():
        st.warning("MOCK_MODE is on. Transcripts come from the written scripts and flags from a keyword heuristic. "
                   "For testing the screens only.")
    c = connect()
    try:
        role = st.radio("View as", ROLES, horizontal=True, key="role")
        if role == "Head of Collections":
            me = c.execute("SELECT id, name FROM user WHERE role = 'head'").fetchone()
            st.caption(f"Signed in as {me['name']}: sees all three offices.")
        else:
            db_role = "caller" if role == "Caller" else "manager"
            users = [dict(r) for r in c.execute(
                """SELECT u.id, u.name, o.name AS office FROM user u JOIN office o ON o.id = u.office_id
                   WHERE u.role = ?
                   ORDER BY (SELECT COUNT(*) FROM call c JOIN user cu ON cu.id = c.caller_id
                             WHERE c.status = 'processed'
                               AND (c.caller_id = u.id OR cu.manager_id = u.id)) DESC, u.name""",
                (db_role,)).fetchall()]
            me = st.selectbox(role, users, key=f"user_{db_role}",
                              format_func=lambda u: f"{u['name']} ({u['office']})")
            if role == "Manager":
                st.caption("Sees only the callers in their team.")
            else:
                st.caption("Sees only their own calls.")
        st.divider()
        page = st.radio("Screen", PAGES, horizontal=True, key="nav", index=1, label_visibility="collapsed")
        if page == "Upload":
            page_upload(c, role)
        elif page == "Call list":
            page_list(c, role, me["id"])
        elif page == "Call review":
            page_review(c, role, me["id"])
        else:
            page_dashboard(c, role, me["id"])
    finally:
        c.close()


main()
