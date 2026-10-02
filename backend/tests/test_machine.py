import itertools

import pytest

from app.learning_engine.machine import (
    REVEAL_STATES,
    WORKING_STATES,
    Progress,
    TransitionError,
    allowed_events,
    apply,
)
from app.learning_engine.states import Event, Outcome, State

START = Progress()


def run(p: Progress, *steps):
    for step in steps:
        if isinstance(step, tuple):
            event, kwargs = step
            p = apply(p, event, **kwargs)
        else:
            p = apply(p, step)
    return p


WRONG = (Event.SUBMIT_ATTEMPT, {"is_correct": False})
RIGHT = (Event.SUBMIT_ATTEMPT, {"is_correct": True})


def test_starts_at_question_received():
    assert START.state is State.QUESTION_RECEIVED
    assert START.outcome is None


def test_no_unconfirmed_jump_from_question_received_to_solution():
    with pytest.raises(TransitionError) as e:
        apply(START, Event.REQUEST_SOLUTION)
    assert e.value.code == "confirm_required"


def test_confirmed_solution_request_is_honoured_and_recorded():
    p = apply(START, Event.REQUEST_SOLUTION, confirmed=True)
    assert p.state is State.FINAL_SOLUTION
    assert p.outcome is Outcome.NEEDED_SOLUTION


def test_solution_needs_no_confirmation_after_any_effort():
    after_hint = apply(START, Event.REQUEST_HINT)
    assert apply(after_hint, Event.REQUEST_SOLUTION).state is State.FINAL_SOLUTION
    after_attempt = run(START, WRONG)
    assert apply(after_attempt, Event.REQUEST_SOLUTION).state is State.FINAL_SOLUTION


def test_hint_ladder_order():
    p = run(START, Event.REQUEST_HINT)
    assert (p.state, p.hint_level) == (State.CONCEPT_HINT, 1)
    p = run(p, Event.REQUEST_HINT)
    assert (p.state, p.hint_level) == (State.STRUCTURAL_HINT, 2)


def test_strong_hint_requires_a_failed_attempt():
    p = run(START, Event.REQUEST_HINT, Event.REQUEST_HINT)
    with pytest.raises(TransitionError) as e:
        apply(p, Event.REQUEST_HINT)
    assert e.value.code == "attempt_required"
    p = run(p, WRONG, Event.REQUEST_HINT)
    assert (p.state, p.hint_level) == (State.STRONG_HINT, 3)


def test_hints_exhausted_after_strong_hint():
    p = run(START, WRONG, Event.REQUEST_HINT, Event.REQUEST_HINT, Event.REQUEST_HINT)
    with pytest.raises(TransitionError) as e:
        apply(p, Event.REQUEST_HINT)
    assert e.value.code == "hints_exhausted"


def test_wrong_attempt_goes_to_error_analysis_and_counts():
    p = run(START, WRONG, WRONG)
    assert p.state is State.ERROR_ANALYSIS
    assert p.failed_attempts == 2
    assert not p.solved


def test_retry_after_error_can_succeed():
    p = run(START, WRONG, RIGHT)
    assert p.state is State.SOLVED
    assert p.outcome is Outcome.INDEPENDENT


def test_outcome_with_hints():
    p = run(START, Event.REQUEST_HINT, RIGHT)
    assert p.outcome is Outcome.WITH_HINTS


def test_submit_requires_evaluation_result():
    with pytest.raises(ValueError):
        apply(START, Event.SUBMIT_ATTEMPT)


def test_finish_path_explanation_then_practice():
    p = run(START, RIGHT, Event.REQUEST_EXPLANATION, Event.REQUEST_PRACTICE)
    assert p.state is State.SIMILAR_PRACTICE
    p = run(START, WRONG, Event.REQUEST_SOLUTION, Event.REQUEST_PRACTICE)
    assert p.state is State.SIMILAR_PRACTICE


def test_cannot_request_solution_or_hint_after_solving():
    p = run(START, RIGHT)
    for event in (Event.REQUEST_SOLUTION, Event.REQUEST_HINT, Event.SUBMIT_ATTEMPT):
        with pytest.raises(TransitionError):
            apply(p, event, is_correct=True, confirmed=True)


def test_similar_practice_is_terminal():
    p = run(START, RIGHT, Event.REQUEST_PRACTICE)
    assert allowed_events(p) == []


def _reachable_states(max_depth: int = 7) -> set[Progress]:
    seen = {START}
    frontier = {START}
    for _ in range(max_depth):
        nxt = set()
        for p, event, correct in itertools.product(frontier, Event, (True, False)):
            try:
                q = apply(p, event, is_correct=correct, confirmed=True)
            except TransitionError:
                continue
            if q not in seen:
                nxt.add(q)
        seen |= nxt
        frontier = nxt
    return seen


def test_solution_only_ever_revealed_via_explicit_request_or_solving():
    """Exhaustive: every reachable reveal state was reached through a correct
    submission or an explicit REQUEST_SOLUTION, never anything else."""
    for p in _reachable_states():
        if p.state in REVEAL_STATES:
            assert p.solved or p.saw_solution, p


def test_allowed_events_matches_apply():
    for p in _reachable_states():
        for event in Event:
            listed = event in allowed_events(p)
            try:
                apply(p, event, is_correct=False, confirmed=True)
                works = True
            except TransitionError:
                works = False
            assert listed == works, (p, event)


def test_working_states_always_offer_an_attempt():
    for p in _reachable_states():
        if p.state in WORKING_STATES:
            assert Event.SUBMIT_ATTEMPT in allowed_events(p)
