"""SQL Mitra learner UI. All teaching logic lives in the API; this file only
renders state and sends events. Buttons are enabled from `allowed_events`."""

import uuid

import pandas as pd
import streamlit as st
from api_client import Api, ApiError, default_api

LEVELS = {"easy": "Beginner", "medium": "Intermediate", "hard": "Advanced"}
MAX_HINTS = 3
AVATARS = {"assistant": "🧑‍🏫", "user": "🧑‍🎓"}
MODES = ["📝 Practice", "🔍 Explain Error", "📊 My Progress"]
OUTCOME_LABELS = {
    "independent": "✅ మీరే solve చేశారు",
    "with_hints": "💡 Hints తో solve చేశారు",
    "needed_solution": "🏳 Solution చూశారు",
    "in_progress": "… ఇంకా పూర్తి కాలేదు",
}
# Widgets whose values must survive while another mode is shown (Streamlit drops
# the state of widgets that are not drawn in a run).
KEPT_WIDGETS = ("topic", "question_pick", "sql", "err_text", "err_sql")
SAMPLE_ERRORS = {
    "MySQL": "ERROR 1054 (42S22): Unknown column 'cancelled' in 'where clause'",
    "PostgreSQL": 'ERROR:  column "orders.city" must appear in the GROUP BY clause '
    "or be used in an aggregate function",
    "BigQuery": "Syntax error: Expected end of input but got keyword WHERE at [3:1]",
}

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
FINISHED = {"SOLVED", "FINAL_SOLUTION", "EXPLANATION", "SIMILAR_PRACTICE"}

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
ss.setdefault("last_sql", None)
ss.setdefault("err_result", None)
for _k in KEPT_WIDGETS:
    if _k in ss:
        ss[f"_kept_{_k}"] = ss[_k]


def restore_widgets() -> None:
    for k in KEPT_WIDGETS:
        if k not in ss and f"_kept_{k}" in ss:
            ss[k] = ss[f"_kept_{k}"]


# ---- actions (run as button callbacks, before the next render) --------------


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
    ss.last_sql = None
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
        ss.last_sql = sql
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


def explain_attempt_error(error: str) -> None:
    try:
        with st.spinner("Error ని చదువుతున్నాం..."):
            r = api().explain_error(error, sql=ss.last_sql, attempt_id=ss.turn["attempt_id"])
    except ApiError as e:
        _notice(e.message)
        return
    ss.transcript.append(
        {
            "role": "assistant",
            "notice": False,
            "text": f"**🔍 Error explanation**\n\n{r['message']}",
        }
    )


def explain_pasted_error() -> None:
    error = ss.get("err_text", "").strip()
    if not error:
        ss.err_result = {"notice": "ముందు database error ని paste చేయండి."}
        return
    try:
        with st.spinner("Error ని చదువుతున్నాం..."):
            ss.err_result = api().explain_error(error, sql=ss.get("err_sql") or None)
    except ApiError as e:
        ss.err_result = {"notice": e.message}


def load_sample(name: str) -> None:
    ss.err_text = SAMPLE_ERRORS[name]
    ss.err_sql = ""
    ss.err_result = None


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


def banner() -> None:
    st.html(
        '<div class="mitra-banner"><h1>Telugu–English SQL Learning Assistant</h1>'
        "<p>Answer ఇవ్వను. Answer మీరే కనుక్కునేలా నేర్పిస్తా.</p></div>"
    )


# ---- views -------------------------------------------------------------------


def practice_sidebar() -> None:
    restore_widgets()
    if "topic" not in ss and ss.question_id:
        ss.topic = by_id[ss.question_id]["topic"]
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


def mentor_actions(turn: dict | None) -> None:
    b1, b2, b3 = st.columns(3)
    if turn and turn["state"] in FINISHED:
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


def result_panel(evaluation: dict) -> None:
    show, text = VERDICTS.get(evaluation["verdict"], (st.info, evaluation["verdict"]))
    show(text)
    if evaluation["error"]:
        st.code(evaluation["error"], language=None)
        st.button(
            "🔍 ఈ error అర్థం ఏంటి?",
            on_click=explain_attempt_error,
            args=(evaluation["error"],),
        )
    if evaluation["columns"]:
        cols, seen = [], {}
        for c in evaluation["columns"]:
            seen[c] = seen.get(c, 0) + 1
            cols.append(c if seen[c] == 1 else f"{c} ({seen[c]})")
        st.caption(f"మీ query result: {evaluation['total_rows_shown']} row(s)")
        st.dataframe(
            pd.DataFrame(evaluation["rows"], columns=cols), hide_index=True, width="stretch"
        )
        if evaluation["truncated"]:
            st.caption("Result పెద్దగా ఉంది, మొదటి rows మాత్రమే చూపిస్తున్నాం.")


def practice_view() -> None:
    if ss.question_pick != ss.question_id:
        start_question(ss.question_pick)
    question = by_id[ss.question_id]
    turn = ss.turn

    banner()
    level = LEVELS.get(question["difficulty"], question["difficulty"])
    st.markdown(f"**Current Topic:** {question['topic']} &nbsp;·&nbsp; **Level:** {level}")

    # Mentor actions sit with the question so they are reachable on a phone
    # without scrolling past the editor and the tables.
    with st.container(border=True):
        st.markdown("**Question**")
        st.markdown(question["prompt_text"])
        if turn:
            st.caption(
                f"💡 Hints {turn['hint_level']}/{MAX_HINTS} · "
                f"తప్పు attempts: {turn['failed_attempts']} · "
                f"{STATE_LABELS.get(turn['state'], turn['state'])}"
            )
        mentor_actions(turn)

    left, right = st.columns([11, 9], gap="large")
    with left:
        st.text_area(
            "✍️ Write Query", key="sql", height=170, placeholder="SELECT ...\nFROM ...\nWHERE ..."
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
            result_panel(evaluation)

    with right:
        st.markdown("#### AI Mentor")
        # Fixed height only once the chat is long, so a short chat leaves no empty box.
        box = st.container(height=520) if len(ss.transcript) > 3 else st.container()
        with box:
            for msg in ss.transcript:
                with st.chat_message(msg["role"], avatar=AVATARS[msg["role"]]):
                    if msg["notice"]:
                        st.info(msg["text"])
                    else:
                        st.markdown(msg["text"])

    with st.expander("🗂 Practice tables (ఏ columns ఉన్నాయో చూడండి)"):
        for table in ss.schema:
            st.markdown(f"**{table['name']}** · {table['row_count']} rows")
            st.caption(", ".join(f"`{c['name']}` {c['type']}" for c in table["columns"]))
            st.dataframe(
                pd.DataFrame(table["sample_rows"], columns=[c["name"] for c in table["columns"]]),
                hide_index=True,
                width="stretch",
            )


def explain_error_view() -> None:
    restore_widgets()
    banner()
    st.markdown("### 🔍 Explain Error")
    st.markdown(
        "MySQL, PostgreSQL, BigQuery, Oracle లేదా SQLite లో వచ్చిన error ని ఇక్కడ paste చేయండి. "
        "Error అర్థం, కారణం, ఎక్కడ చూడాలి, ఒక hint చెబుతాం. **Query ని మేము rewrite చేయం**, "
        "fix మీరే చేయాలి."
    )
    st.text_area(
        "Database error",
        key="err_text",
        height=110,
        placeholder='ఉదా: ERROR:  column "cancelled" does not exist',
    )
    st.text_area("మీ query (optional)", key="err_sql", height=110, placeholder="SELECT ...")
    st.button("🔍 Explain Error", type="primary", on_click=explain_pasted_error)
    st.caption("Example errors:")
    cols = st.columns(len(SAMPLE_ERRORS))
    for col, name in zip(cols, SAMPLE_ERRORS, strict=True):
        col.button(name, on_click=load_sample, args=(name,), width="stretch")

    result = ss.err_result
    if not result:
        return
    if "notice" in result:
        st.info(result["notice"])
        return
    with st.container(border=True):
        detected = result["dialect_name"] or "Database"
        st.caption(f"{detected} error · {result['category'].replace('_', ' ')}")
        st.markdown(result["message"])


def progress_view() -> None:
    banner()
    st.markdown("### 📊 My Progress")
    try:
        p = api().progress(ss.learner_id)
    except ApiError as e:
        st.error(e.message)
        return
    if not p["attempted"]:
        st.info("ఇంకా ఏ question try చేయలేదు. **📝 Practice** లో మొదలుపెట్టండి.")
        return

    st.progress(p["overall_percent"] / 100, text=f"SQL Progress: {p['overall_percent']}%")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("✅ మీరే solve", p["solved_independently"])
    m2.metric("💡 Hints తో", p["solved_with_hints"])
    m3.metric("🏳 Solution చూసినవి", p["needed_solution"])
    m4.metric(
        "🎯 Accuracy",
        f"{p['accuracy_percent']}%" if p["accuracy_percent"] is not None else "–",
        help="Correct submissions ÷ మొత్తం submissions",
    )

    st.markdown("#### Topics")
    for t in p["topics"]:
        st.progress(
            t["mastery_percent"] / 100,
            text=f"{t['topic']} · {t['solved']}/{t['total']} solved · {t['mastery_percent']}%",
        )
    if p["strong_topics"]:
        st.success("Strong: " + ", ".join(p["strong_topics"]))
    if p["weak_topics"]:
        st.warning("ఇంకా practice కావాలి: " + ", ".join(p["weak_topics"]))

    st.markdown("#### మీరు ఎక్కువగా చేసే mistakes")
    if p["mistakes"]:
        for m in p["mistakes"]:
            st.markdown(f"- {m['label']} · **{m['count']}** సార్లు")
    else:
        st.caption("ఇప్పటివరకు common mistakes ఏమీ కనిపించలేదు.")

    st.markdown("#### Questions")
    rows = [
        {
            "Topic": by_id[qid]["topic"],
            "Question": by_id[qid]["prompt_text"],
            "Result": OUTCOME_LABELS.get(outcome, outcome),
        }
        for qid, outcome in p["question_outcomes"].items()
        if qid in by_id
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


# ---- layout ------------------------------------------------------------------

with st.sidebar:
    st.markdown('<p class="mitra-brand">SQL Mitra</p>', unsafe_allow_html=True)
    st.caption("by Automation Lifestyle Hub")
    mode = st.radio("Mode", MODES, key="mode", label_visibility="collapsed")
    st.divider()
    if mode == MODES[0]:
        practice_sidebar()

if mode == MODES[0]:
    practice_view()
elif mode == MODES[1]:
    explain_error_view()
else:
    progress_view()
