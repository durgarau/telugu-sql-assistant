import pytest

from .helpers import event, start


def test_questions_never_expose_solution_or_hints(client):
    r = client.get("/questions")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 5
    for q in body:
        assert set(q) == {"id", "topic", "difficulty", "prompt_text"}


def test_questions_come_in_curriculum_order(client):
    topics = [q["topic"] for q in client.get("/questions").json()]
    assert list(dict.fromkeys(topics)) == ["SELECT", "WHERE", "ORDER BY", "GROUP BY"]


@pytest.mark.parametrize(
    ("solved", "expected_next"),
    [
        ("where-cancelled-orders", "where-delivered-orders"),  # same topic first
        ("select-customer-name-city", "where-cancelled-orders"),  # then same level, onward
        ("group-by-city-order-count", "order-by-top-5-amount"),  # last topic: nearest other
    ],
)
def test_similar_question_stays_at_the_learners_level(client, solved, expected_next):
    aid = start(client, solved)["attempt_id"]
    event(client, aid, "REQUEST_SOLUTION", confirmed=True)
    t = event(client, aid, "REQUEST_PRACTICE").json()
    assert t["suggested_question_id"] == expected_next


def test_practice_schema_lists_tables_with_samples(client):
    tables = {t["name"]: t for t in client.get("/practice/schema").json()}
    assert set(tables) == {"customers", "orders"}
    assert [c["name"] for c in tables["orders"]["columns"]][:2] == ["order_id", "customer_id"]
    assert tables["orders"]["row_count"] == 22
    assert len(tables["customers"]["sample_rows"]) == 3


def test_unknown_question_404(client):
    r = client.post("/attempts", json={"learner_id": "x", "question_id": "nope"})
    assert r.status_code == 404


def test_learner_id_is_validated(client):
    r = client.post(
        "/attempts", json={"learner_id": "<script>", "question_id": "where-cancelled-orders"}
    )
    assert r.status_code == 422


def test_full_guided_loop_to_independent_solve(client):
    t = start(client)
    assert t["state"] == "QUESTION_RECEIVED"
    assert t["solution_needs_confirmation"] is True
    aid = t["attempt_id"]

    t = event(client, aid, "EXPLAIN_QUESTION").json()
    assert t["state"] == "QUESTION_EXPLAINED"

    t = event(client, aid, "REQUEST_HINT").json()
    assert t["state"] == "CONCEPT_HINT" and "`WHERE`" in t["mentor_message"]

    t = event(client, aid, "REQUEST_HINT").json()
    assert t["state"] == "STRUCTURAL_HINT" and "____" in t["mentor_message"]

    r = event(client, aid, "REQUEST_HINT")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "attempt_required"

    wrong = "SELECT * FROM orders WHERE status = cancelled"
    t = event(client, aid, "SUBMIT_ATTEMPT", sql=wrong).json()
    assert t["state"] == "ERROR_ANALYSIS" and t["failed_attempts"] == 1
    assert "cancelled'" not in t["mentor_message"]

    t = event(client, aid, "REQUEST_HINT").json()
    assert t["state"] == "STRONG_HINT"

    right = "select * from orders where status='cancelled';"
    t = event(client, aid, "SUBMIT_ATTEMPT", sql=right).json()
    assert t["state"] == "SOLVED" and t["outcome"] == "with_hints"

    t = event(client, aid, "REQUEST_EXPLANATION").json()
    assert t["state"] == "EXPLANATION" and "WHERE status" in t["mentor_message"]

    t = event(client, aid, "REQUEST_PRACTICE").json()
    assert t["state"] == "SIMILAR_PRACTICE"
    assert t["suggested_question_id"] == "where-delivered-orders"
    assert t["allowed_events"] == []


def test_solution_requires_confirmation_before_any_effort(client):
    aid = start(client)["attempt_id"]
    r = event(client, aid, "REQUEST_SOLUTION")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "confirm_required"

    t = event(client, aid, "REQUEST_SOLUTION", confirmed=True).json()
    assert t["state"] == "FINAL_SOLUTION"
    assert t["outcome"] == "needed_solution"
    assert "WHERE status = 'cancelled'" in t["mentor_message"]


def test_submit_without_sql_is_rejected(client):
    aid = start(client)["attempt_id"]
    r = event(client, aid, "SUBMIT_ATTEMPT")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "sql_required"


def test_sql_only_allowed_on_submit(client):
    aid = start(client)["attempt_id"]
    r = event(client, aid, "REQUEST_HINT", sql="SELECT 1")
    assert r.status_code == 422


def test_oversized_sql_rejected(client):
    aid = start(client)["attempt_id"]
    r = event(client, aid, "SUBMIT_ATTEMPT", sql="SELECT " + "x," * 5000)
    assert r.status_code == 422


def test_get_attempt_resumes_with_last_message(client):
    aid = start(client)["attempt_id"]
    hint = event(client, aid, "REQUEST_HINT").json()
    r = client.get(f"/attempts/{aid}")
    assert r.status_code == 200
    assert r.json()["state"] == "CONCEPT_HINT"
    assert r.json()["mentor_message"] == hint["mentor_message"]


def test_equivalent_query_written_differently_is_accepted(client):
    aid = start(client, "group-by-city-order-count")["attempt_id"]
    sql = "select o.city, count(o.order_id) as total_orders from orders o group by o.city"
    t = event(client, aid, "SUBMIT_ATTEMPT", sql=sql).json()
    assert t["state"] == "SOLVED"
    assert t["outcome"] == "independent"
    assert t["evaluation"]["verdict"] == "correct"
    assert len(t["evaluation"]["rows"]) == 8


def test_wrong_attempt_returns_learner_rows_and_specific_feedback(client):
    aid = start(client)["attempt_id"]
    t = event(client, aid, "SUBMIT_ATTEMPT", sql="SELECT * FROM orders WHERE status = cancelled")
    body = t.json()
    assert body["state"] == "ERROR_ANALYSIS"
    assert body["evaluation"]["verdict"] == "runtime_error"
    assert body["evaluation"]["mistakes"] == ["missing_quotes"]
    assert "no such column: cancelled" in body["evaluation"]["error"]
    assert "single quotes" in body["mentor_message"]

    body = event(client, aid, "SUBMIT_ATTEMPT", sql="SELECT * FROM orders").json()
    ev = body["evaluation"]
    assert ev["verdict"] == "wrong_result" and ev["total_rows_shown"] == 22
    assert ev["columns"][:2] == ["order_id", "customer_id"]
    assert "22 row(s)" in body["mentor_message"]


def test_destructive_sql_is_rejected_without_using_an_attempt(client):
    aid = start(client)["attempt_id"]
    r = event(client, aid, "SUBMIT_ATTEMPT", sql="DROP TABLE orders")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "query_not_allowed"
    t = client.get(f"/attempts/{aid}").json()
    assert t["state"] == "QUESTION_RECEIVED" and t["failed_attempts"] == 0


def test_mistake_tags_are_stored_for_mistake_memory(client):
    from sqlalchemy import select

    from app.database.models import AttemptEvent

    aid = start(client, "order-by-top-5-amount")["attempt_id"]
    event(
        client,
        aid,
        "SUBMIT_ATTEMPT",
        sql="SELECT order_id, amount FROM orders ORDER BY amount LIMIT 5",
    )
    with client.app.state.session_factory() as db:
        row = db.scalars(select(AttemptEvent)).one()
    assert row.verdict == "wrong_result"
    assert row.mistake_tags == ["order_direction"]


def test_runtime_guard_replaces_a_leaking_hint(client, monkeypatch):
    from app.learning_engine import mentor

    monkeypatch.setattr(mentor, "compose", lambda p, q, **_kw: f"Easy! {q.correct_sql}")
    aid = start(client)["attempt_id"]
    t = event(client, aid, "REQUEST_HINT").json()
    assert t["mentor_message"] == mentor.SAFE_FALLBACK


def test_attempt_ids_are_not_guessable(client):
    aid = start(client)["attempt_id"]
    assert len(aid) == 32 and not aid.isdigit()
