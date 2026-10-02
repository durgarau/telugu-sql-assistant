from .helpers import event, start


def test_questions_never_expose_solution_or_hints(client):
    r = client.get("/questions")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 5
    for q in body:
        assert set(q) == {"id", "topic", "difficulty", "prompt_text"}


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


def test_runtime_guard_replaces_a_leaking_hint(client, monkeypatch):
    from app.learning_engine import mentor

    monkeypatch.setattr(mentor, "compose", lambda p, q: f"Easy! {q.correct_sql}")
    aid = start(client)["attempt_id"]
    t = event(client, aid, "REQUEST_HINT").json()
    assert t["mentor_message"] == mentor.SAFE_FALLBACK


def test_attempt_ids_are_not_guessable(client):
    aid = start(client)["attempt_id"]
    assert len(aid) == 32 and not aid.isdigit()
