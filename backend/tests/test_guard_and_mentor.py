import json

import pytest

from app.config import Settings
from app.learning_engine import mentor
from app.learning_engine.guard import leaks_solution
from app.learning_engine.machine import REVEAL_STATES, Progress
from app.learning_engine.states import State

QUESTIONS = json.loads(Settings().questions_path.read_text(encoding="utf-8"))


def test_guard_ignores_whitespace_and_case():
    sql = "SELECT *\nFROM orders\nWHERE status = 'cancelled'"
    skeleton = "SELECT *\nFROM ____\nWHERE status = ____"
    assert leaks_solution("try: select * from   orders where status='cancelled';", sql, skeleton)
    assert leaks_solution("WHERE   STATUS='Cancelled'", sql, skeleton)
    assert not leaks_solution(skeleton, sql, skeleton)


@pytest.mark.parametrize("q", QUESTIONS, ids=lambda q: q["id"])
def test_authored_hints_never_contain_the_solution(q):
    for field in ("structure_hint", "strong_hint"):
        assert not leaks_solution(q[field], q["correct_sql"], q["structure_hint"]), field


@pytest.mark.parametrize("q", QUESTIONS, ids=lambda q: q["id"])
@pytest.mark.parametrize("state", list(State))
def test_mentor_messages_only_show_solution_in_reveal_states(q, state):
    content = mentor.QuestionContent(
        **{
            k: q[k]
            for k in (
                "id",
                "prompt_text",
                "concepts",
                "structure_hint",
                "strong_hint",
                "correct_sql",
            )
        }
    )
    text = mentor.compose(Progress(state=state, failed_attempts=1, hint_level=1), content)
    assert text.strip()
    if state not in REVEAL_STATES:
        assert not leaks_solution(text, q["correct_sql"], q["structure_hint"])
