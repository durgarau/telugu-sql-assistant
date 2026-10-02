"""Drives the real Streamlit UI against the real backend, in-process.
FastAPI's TestClient is an httpx.Client, so the UI's Api wrapper uses it as is."""

from pathlib import Path

import httpx
import pytest
from api_client import Api
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from app.config import Settings
from app.main import create_app

SCRIPT = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")


@pytest.fixture
def backend():
    app = create_app(Settings(database_url="sqlite:///:memory:"), provider_factory=lambda _s: None)
    with TestClient(app) as c:
        yield c


def _launch(api: Api) -> AppTest:
    at = AppTest.from_file(SCRIPT, default_timeout=15)
    at.session_state["api"] = api
    at.run()
    return at


@pytest.fixture
def at(backend):
    at = _launch(Api(backend))
    assert not at.exception
    return at


def click(at: AppTest, label: str) -> AppTest:
    matches = [b for b in at.button if b.label == label]
    assert matches, f"no button {label!r}; have {[b.label for b in at.button]}"
    matches[0].click().run()
    assert not at.exception, at.exception
    return at


def button(at: AppTest, label: str):
    return next(b for b in at.button if b.label == label)


def transcript(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown) + "\n".join(i.value for i in at.info)


def submit(at: AppTest, sql: str) -> AppTest:
    at.text_area(key="sql").input(sql)
    return click(at, "▶ Check Query")


def test_first_load_starts_the_first_question(at):
    assert at.session_state["question_id"] == "select-customer-name-city"
    assert at.session_state["turn"]["state"] == "QUESTION_RECEIVED"
    assert "కొత్త question" in transcript(at)
    assert not button(at, "▶ Check Query").disabled
    assert not button(at, "🏳 Solution").disabled
    assert all(b.label != "📖 Line-by-line" for b in at.button)


def test_hint_ladder_and_strong_hint_needs_an_attempt(at):
    click(at, "💡 Hint")
    assert at.session_state["turn"]["state"] == "CONCEPT_HINT"
    assert "Hints 1/3" in at.caption[0].value
    click(at, "💡 Hint")
    assert at.session_state["turn"]["state"] == "STRUCTURAL_HINT"
    click(at, "💡 Hint")
    assert at.session_state["turn"]["state"] == "STRUCTURAL_HINT"
    assert any("Strong hint" in i.value for i in at.info)


def test_wrong_attempt_shows_feedback_and_learner_rows(at):
    submit(at, "SELECT name FROM customers")
    assert at.session_state["turn"]["state"] == "ERROR_ANALYSIS"
    assert any("match అవ్వలేదు" in w.value for w in at.warning)
    assert len(at.dataframe) >= 1
    assert at.dataframe[0].value.shape == (11, 1)


def test_syntax_error_shows_database_message(at):
    submit(at, "SELECT name FORM customers")
    assert any("Syntax error" in e.value for e in at.error)
    assert any("syntax error" in c.value for c in at.code)


def test_early_solution_asks_for_confirmation(at):
    click(at, "🏳 Solution")
    assert at.session_state["turn"]["state"] == "QUESTION_RECEIVED"
    assert at.session_state["pending_confirm"]
    click(at, "Solution చూపించు")
    assert at.session_state["turn"]["state"] == "FINAL_SOLUTION"
    assert "SELECT name, city" in transcript(at)
    assert not button(at, "📖 Line-by-line").disabled


def test_confirm_box_can_redirect_to_a_hint(at):
    click(at, "🏳 Solution")
    click(at, "💡 ముందు hint try చేస్తా")
    assert at.session_state["turn"]["state"] == "CONCEPT_HINT"
    assert at.session_state["pending_confirm"] is None


def test_full_loop_solve_explain_and_move_to_similar_question(at):
    submit(at, "select name, city from customers")
    assert at.session_state["turn"]["state"] == "SOLVED"
    assert any("Correct" in s.value for s in at.success)

    click(at, "📖 Line-by-line")
    assert at.session_state["turn"]["state"] == "EXPLANATION"
    click(at, "🔁 Similar question")
    assert at.session_state["turn"]["state"] == "SIMILAR_PRACTICE"

    click(at, "తర్వాత question →")
    assert at.session_state["question_id"] != "select-customer-name-city"
    assert at.session_state["turn"]["state"] == "QUESTION_RECEIVED"
    assert at.text_area(key="sql").value == ""


def test_empty_submit_gives_a_gentle_notice(at):
    click(at, "▶ Check Query")
    assert any("ఖాళీగా" in i.value for i in at.info)
    assert at.session_state["turn"]["state"] == "QUESTION_RECEIVED"


def test_destructive_sql_is_refused_in_the_ui(at):
    submit(at, "DROP TABLE customers")
    assert any("SELECT queries మాత్రమే" in i.value for i in at.info)
    assert at.session_state["turn"]["failed_attempts"] == 0


def test_switching_topic_starts_that_topics_question(at):
    at.selectbox(key="topic").select("WHERE").run()
    assert at.session_state["question_id"] == "where-cancelled-orders"
    assert at.session_state["transcript"][0]["text"].startswith("కొత్త question")


def test_practice_tables_are_shown(at):
    assert any("customers" in m.value for m in at.markdown)
    assert any("orders" in m.value for m in at.markdown)


PRACTICE, EXPLAIN, PROGRESS = "📝 Practice", "🔍 Explain Error", "📊 My Progress"


def switch_mode(at: AppTest, mode: str) -> AppTest:
    at.radio(key="mode").set_value(mode).run()
    assert not at.exception, at.exception
    return at


def test_switching_modes_keeps_the_question_draft_and_chat(at):
    click(at, "💡 Hint")
    at.text_area(key="sql").input("SELECT name")
    switch_mode(at, PROGRESS)
    switch_mode(at, PRACTICE)
    assert at.session_state["question_id"] == "select-customer-name-city"
    assert at.session_state["turn"]["state"] == "CONCEPT_HINT"
    assert at.text_area(key="sql").value == "SELECT name"
    assert len(at.session_state["transcript"]) == 2


def test_explain_error_mode_with_a_sample_error(at):
    switch_mode(at, EXPLAIN)
    click(at, "MySQL")
    assert "Unknown column" in at.text_area(key="err_text").value
    click(at, "🔍 Explain Error")
    assert any("MySQL error" in c.value for c in at.caption)
    text = "\n".join(m.value for m in at.markdown)
    assert "**అర్థం:**" in text and "`cancelled`" in text


def test_explain_error_mode_needs_an_error(at):
    switch_mode(at, EXPLAIN)
    click(at, "🔍 Explain Error")
    assert any("paste" in i.value for i in at.info)


def test_explain_this_error_button_inside_practice(at):
    at.selectbox(key="topic").select("WHERE").run()
    submit(at, "SELECT * FROM orders WHERE status = cancelled")
    click(at, "🔍 ఈ error అర్థం ఏంటి?")
    last = at.session_state["transcript"][-1]["text"]
    assert last.startswith("**🔍 Error explanation**")
    assert "`cancelled`" in last
    assert "status = 'cancelled'" not in last


def test_progress_mode_empty_then_after_solving(at):
    switch_mode(at, PROGRESS)
    assert any("ఇంకా ఏ question" in i.value for i in at.info)

    switch_mode(at, PRACTICE)
    submit(at, "select name, city from customers")
    switch_mode(at, PROGRESS)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["✅ మీరే solve"] == "1"
    assert metrics["🎯 Accuracy"] == "100%"
    assert any("Strong: SELECT" in s.value for s in at.success)


def test_backend_down_shows_a_friendly_error():
    at = _launch(Api(httpx.Client(base_url="http://127.0.0.1:9", timeout=0.5)))
    assert not at.exception
    assert any("connect అవ్వలేకపోయాం" in e.value for e in at.error)
