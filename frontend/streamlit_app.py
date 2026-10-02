"""SQL Mitra learner UI. All teaching logic lives in the API; this file only
renders state and sends events. Buttons are enabled from `allowed_events`."""

import uuid

import pandas as pd
import streamlit as st
from api_client import Api, ApiError, default_api

LEVELS = {"easy": "Beginner", "medium": "Intermediate", "hard": "Advanced"}
MAX_HINTS = 3
AVATARS = {"assistant": "🧑‍🏫", "user": "🧑‍🎓"}

STATE_LABELS = {
    "QUESTION_RECEIVED": "కొత్త question",
    "QUESTION_EXPLAINED": "Question అర్థం చేసుకుంటున్నాం",
    "CONCEPT_HINT": "Hint 1 · concepts",
    "STRUCTURAL_HINT": "Hint 2 · structure",
    "ERROR_ANALYSIS": "Feedback · మళ్ళీ try చేయండి",
    "STRONG_HINT": "Hint 3 · strong hint",
    "SOLVED": "Solved!",
    "FINAL_SOLUTION": "Solution చూశారు",
    "EXPLANATION": "Line-by-line explanation",
    "SIMILAR_PRACTICE": "తర్వాత question",
}
VERDICTS = {
    "correct": (st.success, "Correct! మీ query expected result ఇచ్చింది."),
    "wrong_result": (st.warning, "Query run అయింది, కానీ result question తో match అవ్వలేదు."),
    "syntax_error": (st.error, "Syntax error: query structure లో problem ఉంది."),
    "runtime_error": (st.error, "Query run అవ్వలేదు."),
}

CSS = """
<style>
.mitra-banner {background: linear-gradient(120deg, #0B1A36 0%, #14284F 100%);
  border-bottom: 3px solid #C9A227; border-radius: 10px; padding: 14px 20px; margin-bottom: 14px;}
.mitra-banner h1 {color: #F3D77A; font-size: 1.55rem; margin: 0; padding: 0; line-height: 1.2;}
.mitra-banner p {color: #DCE3F2; margin: 4px 0 0 0; font-size: 0.95rem;}
.mitra-brand {color: #C9A227; font-weight: 700; font-size: 1.25rem; margin-bottom: 0;}
</style>
"""

st.set_page_config(page_title="SQL Mitra", page_icon=":material/database:", layout="wide")
st.html(CSS)


@st.cache_resource
def _shared_api() -> Api:
    return default_api()


def api() -> Api:
    return st.session_state.get("api") or _shared_api()


ss = st.session_state
ss.setdefault("learner_id", uuid.uuid4().hex[:16])
ss.setdefault("turn", None)
ss.setdefault("transcript", [])
ss.setdefault("pending_confirm", None)
ss.setdefault("question_id", None)


def _notice(text: str) -> None:
    ss.transcript.append({"role": "assistant", "notice": True, "text": text})


def _apply(turn: dict) -> None:
    ss.turn = turn
    ss.transcript.append({"role": "assistant", "notice": False, "text": turn["mentor_message"]})


def start_question(question_id: str) -> None:
    ss.question_id = question_id
    ss.turn = None
    ss.transcript = []
    ss.pending_confirm = None
    ss.sql = ""
    try:
        _apply(api().start(ss.learner_id, question_id))
    except ApiError as e:
        _notice(e.message)


def send(event: str, confirmed: bool = False) -> None:
    sql = None
    if event == "SUBMIT_ATTEMPT":
        sql = ss.get("sql", "")
        if not sql.strip():
            _notice("Query ఖాళీగా ఉంది. ముందు SQL రాసి తర్వాత Check నొక్కండి.")
            return
        ss.transcript.append({"role": "user", "notice": False, "text": f"```sql\n{sql}\n```"})
    ss.pending_confirm = None
    try:
        with st.spinner("Mentor ఆలోచిస్తోంది..."):
            _apply(api().send(ss.turn["attempt_id"], event, sql=sql, confirmed=confirmed))
    except ApiError as e:
        if e.code == "confirm_required":
            ss.pending_confirm = e.message
        else:
            _notice(e.message)


def go_to(question_id: str, topic: str) -> None:
    ss.topic = topic
    ss.question_pick = question_id


def allowed(event: str) -> bool:
    return bool(ss.turn) and event in ss.turn["allowed_events"]


# ---- data ------------------------------------------------------------------

try:
    if "questions" not in ss:
        ss.questions = api().questions()
    if "schema" not in ss:
        ss.schema = api().schema()
except ApiError as e:
    st.error(e.message)
    st.stop()

by_id = {q["id"]: q for q in ss.questions}
topics = list(dict.fromkeys(q["topic"] for q in ss.questions))  # API returns curriculum order

# ---- sidebar ---------------------------------------------------------------

with st.sidebar:
    st.markdown('<p class="mitra-brand">SQL Mitra</p>', unsafe_allow_html=True)
    st.caption("by Automation Lifestyle Hub")
    topic = st.selectbox("Topic", topics, key="topic")
    in_topic = [q["id"] for q in ss.questions if q["topic"] == topic]
    if ss.get("question_pick") not in in_topic:
        ss.question_pick = in_topic[0]
    st.radio(
        "Question",
        in_topic,
        key="question_pick",
        format_func=lambda qid: (
            f"{LEVELS.get(by_id[qid]['difficulty'], '')} · {by_id[qid]['prompt_text'][:42]}…"
        ),
    )
    st.divider()
    st.button(
        "↺ ఈ question మళ్ళీ మొదలుపెట్టు",
        on_click=lambda: start_question(ss.question_id),
        width="stretch",
    )
    with st.expander("ఇది ఎలా పనిచేస్తుంది?"):
        st.markdown(
            "1. Question చదవండి, అవసరమైతే **Explain** నొక్కండి.\n"
            "2. Stuck అయితే **Hint** అడగండి (3 levels).\n"
            "3. Query రాసి **Check Query** నొక్కండి.\n"
            "4. Feedback చూసి మళ్ళీ try చేయండి.\n"
            "5. చివరగా మాత్రమే solution."
        )

if ss.question_pick != ss.question_id:
    start_question(ss.question_pick)

question = by_id[ss.question_id]
turn = ss.turn

# ---- header ----------------------------------------------------------------

st.html(
    '<div class="mitra-banner"><h1>Telugu–English SQL Learning Assistant</h1>'
    "<p>Answer ఇవ్వను. Answer మీరే కనుక్కునేలా నేర్పిస్తా.</p></div>"
)
level = LEVELS.get(question["difficulty"], question["difficulty"])
st.markdown(f"**Current Topic:** {question['topic']} &nbsp;·&nbsp; **Level:** {level}")

with st.container(border=True):
    st.markdown("**Question**")
    st.markdown(question["prompt_text"])
    if turn:
        st.caption(
            f"💡 Hints {turn['hint_level']}/{MAX_HINTS} · "
            f"తప్పు attempts: {turn['failed_attempts']} · "
            f"{STATE_LABELS.get(turn['state'], turn['state'])}"
        )

left, right = st.columns([11, 9], gap="large")

# ---- left: editor and result ----------------------------------------------

with left:
    st.text_area(
        "✍️ Write Query",
        key="sql",
        height=170,
        placeholder="SELECT ...\nFROM ...\nWHERE ...",
    )
    st.button(
        "▶ Check Query",
        type="primary",
        on_click=send,
        args=("SUBMIT_ATTEMPT",),
        disabled=not allowed("SUBMIT_ATTEMPT"),
    )

    evaluation = turn.get("evaluation") if turn else None
    if evaluation:
        show, text = VERDICTS.get(evaluation["verdict"], (st.info, evaluation["verdict"]))
        show(text)
        if evaluation["error"]:
            st.code(evaluation["error"], language=None)
        if evaluation["columns"]:
            cols, seen = [], {}
            for c in evaluation["columns"]:
                seen[c] = seen.get(c, 0) + 1
                cols.append(c if seen[c] == 1 else f"{c} ({seen[c]})")
            st.caption(f"మీ query result: {evaluation['total_rows_shown']} row(s)")
            st.dataframe(
                pd.DataFrame(evaluation["rows"], columns=cols),
                hide_index=True,
                width="stretch",
            )
            if evaluation["truncated"]:
                st.caption("Result పెద్దగా ఉంది, మొదటి rows మాత్రమే చూపిస్తున్నాం.")

    with st.expander("🗂 Practice tables (ఏ columns ఉన్నాయో చూడండి)"):
        for table in ss.schema:
            st.markdown(f"**{table['name']}** · {table['row_count']} rows")
            st.caption(", ".join(f"`{c['name']}` {c['type']}" for c in table["columns"]))
            st.dataframe(
                pd.DataFrame(table["sample_rows"], columns=[c["name"] for c in table["columns"]]),
                hide_index=True,
                width="stretch",
            )

# ---- right: mentor ----------------------------------------------------------

with right:
    st.markdown("#### AI Mentor")
    finished = turn is not None and turn["state"] in {
        "SOLVED",
        "FINAL_SOLUTION",
        "EXPLANATION",
        "SIMILAR_PRACTICE",
    }
    b1, b2, b3 = st.columns(3)
    if finished:
        b1.button(
            "📖 Line-by-line",
            on_click=send,
            args=("REQUEST_EXPLANATION",),
            disabled=not allowed("REQUEST_EXPLANATION"),
            width="stretch",
        )
        b2.button(
            "🔁 Similar question",
            on_click=send,
            args=("REQUEST_PRACTICE",),
            disabled=not allowed("REQUEST_PRACTICE"),
            width="stretch",
        )
    else:
        b1.button(
            "🧠 Explain",
            on_click=send,
            args=("EXPLAIN_QUESTION",),
            disabled=not allowed("EXPLAIN_QUESTION"),
            width="stretch",
        )
        # Stays clickable while working: when no hint is available yet, the
        # server's reply explains why (e.g. "try one query first").
        b2.button(
            "💡 Hint",
            on_click=send,
            args=("REQUEST_HINT",),
            disabled=turn is None,
            width="stretch",
        )
        b3.button(
            "🏳 Solution",
            on_click=send,
            args=("REQUEST_SOLUTION",),
            disabled=not allowed("REQUEST_SOLUTION"),
            width="stretch",
        )

    if ss.pending_confirm:
        with st.container(border=True):
            st.warning(ss.pending_confirm)
            c1, c2 = st.columns(2)
            c1.button("💡 ముందు hint try చేస్తా", on_click=send, args=("REQUEST_HINT",))
            c2.button(
                "Solution చూపించు",
                on_click=send,
                args=("REQUEST_SOLUTION",),
                kwargs={"confirmed": True},
            )

    if turn and turn["state"] == "SIMILAR_PRACTICE" and turn.get("suggested_question_id"):
        nxt = by_id.get(turn["suggested_question_id"])
        if nxt:
            st.button(
                "తర్వాత question →",
                type="primary",
                on_click=go_to,
                args=(nxt["id"], nxt["topic"]),
            )

    with st.container(height=520):
        for msg in ss.transcript:
            with st.chat_message(msg["role"], avatar=AVATARS[msg["role"]]):
                if msg["notice"]:
                    st.info(msg["text"])
                else:
                    st.markdown(msg["text"])
