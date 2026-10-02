import json

import httpx
import pytest
from sqlalchemy import select

from app.ai.base import AIProviderError, ChatMessage
from app.ai.factory import build_provider
from app.ai.openrouter import OpenRouterProvider
from app.config import Settings
from app.database.models import AttemptEvent, Question
from app.learning_engine import ai_mentor
from app.learning_engine.guard import hidden_lines, leaks_solution
from app.learning_engine.machine import REVEAL_STATES, Progress
from app.learning_engine.states import State
from app.prompts.mentor_prompts import AI_STATES, build_messages
from app.sql_engine.evaluator import normalize_sql

from .helpers import FailingProvider, FakeProvider, event, start

QUESTIONS = [
    Question(**q) for q in json.loads(Settings().questions_path.read_text(encoding="utf-8"))
]

# Every (state, hint_level, failed_attempts) the engine can produce for an AI state.
AI_PROGRESS = [
    Progress(state=State.QUESTION_EXPLAINED, hint_level=lvl, failed_attempts=f)
    for lvl in (0, 1, 2, 3)
    for f in (0, 1)
] + [
    Progress(state=State.CONCEPT_HINT, hint_level=1),
    Progress(state=State.STRUCTURAL_HINT, hint_level=2),
    Progress(state=State.STRONG_HINT, hint_level=3, failed_attempts=1),
    *[Progress(state=State.ERROR_ANALYSIS, hint_level=lvl, failed_attempts=1) for lvl in range(4)],
    Progress(state=State.EXPLANATION, hint_level=1, solved=True),
    Progress(state=State.EXPLANATION, saw_solution=True),
]


def _prompt_text(messages: list[ChatMessage]) -> str:
    return "\n".join(m.content for m in messages)


@pytest.mark.parametrize("q", QUESTIONS, ids=lambda q: q.id)
@pytest.mark.parametrize("p", AI_PROGRESS, ids=lambda p: f"{p.state}-h{p.hint_level}")
def test_prompts_carry_only_what_the_learner_has_seen(q, p):
    m = ai_mentor.material_for(p, q, student_sql="SELECT 1")
    text = _prompt_text(build_messages(p.state, m))
    if p.state in REVEAL_STATES:
        assert q.correct_sql in text
        return
    # Checked at the data boundary too, so a future template cannot pick it up.
    assert m.solution_sql is None
    assert not leaks_solution(text, q.correct_sql, q.structure_hint)
    assert (q.structure_hint in text) == (p.hint_level >= 2)
    assert (q.strong_hint in text) == (p.hint_level >= 3)


def test_every_ai_state_has_a_template_and_reveal_states_are_explicit():
    assert {
        State.QUESTION_EXPLAINED,
        State.CONCEPT_HINT,
        State.STRUCTURAL_HINT,
        State.ERROR_ANALYSIS,
        State.STRONG_HINT,
        State.EXPLANATION,
    } == AI_STATES


@pytest.mark.parametrize("q", QUESTIONS, ids=lambda q: q.id)
def test_hidden_lines_are_the_parts_the_learner_must_produce(q):
    lines = hidden_lines(q.correct_sql, q.structure_hint)
    assert lines, "every question must hide at least one answer line"
    for line in lines:
        assert line not in normalize_sql(q.structure_hint)


def test_guard_blocks_a_single_answer_clause():
    q = next(q for q in QUESTIONS if q.id == "group-by-city-order-count")
    assert leaks_solution("Just add `GROUP BY city` 🙂", q.correct_sql, q.structure_hint)
    assert not leaks_solution("`GROUP BY` తర్వాత ఏ column?", q.correct_sql, q.structure_hint)


# ---- end-to-end through the API --------------------------------------------


def test_ai_text_is_used_and_recorded(make_client):
    fake = FakeProvider("AI చెప్పిన hint: ____ ఆలోచించండి")
    c = make_client(fake)
    t = start(c)
    assert fake.calls == []  # QUESTION_RECEIVED stays canned
    aid = t["attempt_id"]

    t = event(c, aid, "REQUEST_HINT").json()
    assert t["mentor_message"].startswith("AI చెప్పిన hint")

    with c.app.state.session_factory() as db:
        sources = db.scalars(select(AttemptEvent.mentor_source)).all()
    assert sources == ["ai"]


def test_structural_hint_always_shows_the_authored_skeleton(make_client):
    c = make_client(FakeProvider("ప్రతి blank గురించి ఆలోచించండి"))
    aid = start(c)["attempt_id"]
    event(c, aid, "REQUEST_HINT")
    t = event(c, aid, "REQUEST_HINT").json()
    assert t["mentor_message"].startswith("```sql\nSELECT *\nFROM ____\nWHERE status = ____\n```")


@pytest.mark.parametrize(
    "leak",
    [
        "Answer: SELECT * FROM orders WHERE status = 'cancelled'",
        "Just write where status = 'cancelled' and submit",
    ],
)
def test_leaking_ai_reply_falls_back_to_canned(make_client, leak):
    c = make_client(FakeProvider(leak))
    aid = start(c)["attempt_id"]
    t = event(c, aid, "REQUEST_HINT").json()
    assert "cancelled'" not in t["mentor_message"]
    assert "`WHERE`" in t["mentor_message"]  # the canned concept hint
    with c.app.state.session_factory() as db:
        assert db.scalars(select(AttemptEvent.mentor_source)).all() == ["canned"]


def test_feedback_may_quote_what_the_learner_wrote(make_client):
    reply = "మీ `GROUP BY city` correct. Alias ____ check చేయండి."
    c = make_client(FakeProvider(reply))
    aid = start(c, "group-by-city-order-count")["attempt_id"]
    t = event(c, aid, "SUBMIT_ATTEMPT", sql="SELECT city, COUNT(*) FROM orders GROUP BY city")
    assert t.json()["mentor_message"] == reply


def test_same_clause_is_blocked_if_the_learner_never_wrote_it(make_client):
    c = make_client(FakeProvider("Just add `GROUP BY city` and alias ____"))
    aid = start(c, "group-by-city-order-count")["attempt_id"]
    t = event(c, aid, "SUBMIT_ATTEMPT", sql="SELECT city, COUNT(*) FROM orders").json()
    assert "group by city" not in t["mentor_message"].lower()


def test_error_analysis_prompt_carries_checker_facts(make_client):
    fake = FakeProvider("ఇంకోసారి ____")
    c = make_client(fake)
    aid = start(c)["attempt_id"]
    event(c, aid, "SUBMIT_ATTEMPT", sql="SELECT * FROM orders WHERE status = cancelled")
    prompt = _prompt_text(fake.calls[-1])
    assert "verified" in prompt and "single quotes" in prompt


def test_provider_failure_falls_back_to_canned(make_client):
    c = make_client(FailingProvider())
    aid = start(c)["attempt_id"]
    r = event(c, aid, "REQUEST_HINT")
    assert r.status_code == 200
    assert "`WHERE`" in r.json()["mentor_message"]


def test_explanation_may_show_the_solution(make_client):
    c = make_client(FakeProvider(lambda msgs: "Line 1: " + msgs[-1].content[-60:]))
    aid = start(c)["attempt_id"]
    event(c, aid, "SUBMIT_ATTEMPT", sql="select * from orders where status='cancelled'")
    t = event(c, aid, "REQUEST_EXPLANATION").json()
    assert "WHERE status = 'cancelled'" in t["mentor_message"]


def test_error_analysis_and_strong_hint_see_the_learners_query(make_client):
    fake = FakeProvider("ఇంకోసారి try చేయండి ____")
    c = make_client(fake)
    aid = start(c)["attempt_id"]
    wrong = "SELECT * FROM orders WHERE status = cancelled"
    event(c, aid, "SUBMIT_ATTEMPT", sql=wrong)
    assert wrong in _prompt_text(fake.calls[-1])

    event(c, aid, "REQUEST_HINT")
    event(c, aid, "REQUEST_HINT")
    event(c, aid, "REQUEST_HINT")
    strong_prompt = _prompt_text(fake.calls[-1])
    assert "stuck after 1 failed attempt" in strong_prompt
    assert wrong in strong_prompt
    assert "do not repeat" in strong_prompt


# ---- OpenRouter adapter ----------------------------------------------------


def _provider(handler) -> OpenRouterProvider:
    return OpenRouterProvider("sk-test", "test/model", transport=httpx.MockTransport(handler))


def test_openrouter_request_shape_and_reply():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "  hi  "}}]})

    out = _provider(handler).complete([ChatMessage("system", "s"), ChatMessage("user", "u")])
    assert out == "hi"
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["model"] == "test/model"
    assert seen["body"]["messages"] == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
    ]


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(500, text="boom"),
        lambda r: httpx.Response(200, text="not json"),
        lambda r: httpx.Response(200, json={"choices": []}),
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "  "}}]}),
    ],
    ids=["http-500", "not-json", "no-choices", "empty"],
)
def test_openrouter_bad_responses_raise_provider_error(handler):
    with pytest.raises(AIProviderError):
        _provider(handler).complete([ChatMessage("user", "u")])


def test_openrouter_network_error_raises_provider_error():
    def handler(request):
        raise httpx.ConnectTimeout("timeout", request=request)

    with pytest.raises(AIProviderError):
        _provider(handler).complete([ChatMessage("user", "u")])


def test_factory_needs_key_and_model():
    assert build_provider(Settings(_env_file=None, openrouter_api_key=None)) is None
    blank = Settings(_env_file=None, openrouter_api_key="", openrouter_model="m")
    assert build_provider(blank) is None
    assert build_provider(Settings(_env_file=None, openrouter_api_key="sk-x")) is None
    p = build_provider(Settings(_env_file=None, openrouter_api_key="sk-x", openrouter_model="m"))
    assert isinstance(p, OpenRouterProvider)
    p.close()


def test_api_key_never_appears_in_settings_repr():
    s = Settings(_env_file=None, openrouter_api_key="sk-secret-123")
    assert "sk-secret-123" not in repr(s)
