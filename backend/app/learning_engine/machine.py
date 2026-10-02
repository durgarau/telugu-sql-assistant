"""Guided-learning state machine. Pure functions only: no I/O, no LLM.

This module is the single authority on what the learner may see next.
The LLM (from M2) only phrases a state this module has already chosen.
"""

from dataclasses import dataclass, replace

from .states import Event, Outcome, State

HINT_LADDER = (State.CONCEPT_HINT, State.STRUCTURAL_HINT, State.STRONG_HINT)
STRONG_HINT_MIN_FAILED_ATTEMPTS = 1

WORKING_STATES = frozenset(
    {
        State.QUESTION_RECEIVED,
        State.QUESTION_EXPLAINED,
        State.CONCEPT_HINT,
        State.STRUCTURAL_HINT,
        State.ERROR_ANALYSIS,
        State.STRONG_HINT,
    }
)
FINISHED_STATES = frozenset({State.SOLVED, State.FINAL_SOLUTION, State.EXPLANATION})
REVEAL_STATES = frozenset({State.SOLVED, State.FINAL_SOLUTION, State.EXPLANATION})


class TransitionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Progress:
    state: State = State.QUESTION_RECEIVED
    hint_level: int = 0
    failed_attempts: int = 0
    solved: bool = False
    saw_solution: bool = False

    @property
    def outcome(self) -> Outcome | None:
        if self.saw_solution:
            return Outcome.NEEDED_SOLUTION
        if self.solved:
            return Outcome.INDEPENDENT if self.hint_level == 0 else Outcome.WITH_HINTS
        return None

    @property
    def solution_needs_confirmation(self) -> bool:
        return self.state in WORKING_STATES and self.hint_level == 0 and self.failed_attempts == 0


def _require(p: Progress, allowed: frozenset[State], event: Event) -> None:
    if p.state not in allowed:
        raise TransitionError(
            "illegal_transition",
            f"ఇప్పుడు ({p.state}) ఈ action ({event}) చేయలేము.",
        )


def apply(
    p: Progress,
    event: Event,
    *,
    is_correct: bool | None = None,
    confirmed: bool = False,
) -> Progress:
    if event is Event.EXPLAIN_QUESTION:
        _require(p, WORKING_STATES, event)
        return replace(p, state=State.QUESTION_EXPLAINED)

    if event is Event.REQUEST_HINT:
        _require(p, WORKING_STATES, event)
        if p.hint_level >= len(HINT_LADDER):
            raise TransitionError(
                "hints_exhausted",
                "Hints అన్నీ అయిపోయాయి. ఇంకో attempt try చేయండి, లేదా solution చూడండి.",
            )
        next_state = HINT_LADDER[p.hint_level]
        if next_state is State.STRONG_HINT and p.failed_attempts < STRONG_HINT_MIN_FAILED_ATTEMPTS:
            raise TransitionError(
                "attempt_required",
                "Strong hint కి ముందు మీరే ఒక query రాసి try చేయండి. Mistake అయినా పర్వాలేదు.",
            )
        return replace(p, state=next_state, hint_level=p.hint_level + 1)

    if event is Event.SUBMIT_ATTEMPT:
        _require(p, WORKING_STATES, event)
        if is_correct is None:
            raise ValueError("SUBMIT_ATTEMPT requires is_correct")
        if is_correct:
            return replace(p, state=State.SOLVED, solved=True)
        return replace(p, state=State.ERROR_ANALYSIS, failed_attempts=p.failed_attempts + 1)

    if event is Event.REQUEST_SOLUTION:
        _require(p, WORKING_STATES, event)
        if p.solution_needs_confirmation and not confirmed:
            raise TransitionError(
                "confirm_required",
                "ఇంకా ఒక్క hint కూడా చూడలేదు, ఒక్క attempt కూడా చేయలేదు. "
                "Answer చూసే ముందు ఒక hint try చేద్దామా? "
                "అయినా solution కావాలంటే confirm చేయండి.",
            )
        return replace(p, state=State.FINAL_SOLUTION, saw_solution=True)

    if event is Event.REQUEST_EXPLANATION:
        _require(p, frozenset({State.SOLVED, State.FINAL_SOLUTION}), event)
        return replace(p, state=State.EXPLANATION)

    if event is Event.REQUEST_PRACTICE:
        _require(p, FINISHED_STATES, event)
        return replace(p, state=State.SIMILAR_PRACTICE)

    raise AssertionError(f"unhandled event {event}")


def allowed_events(p: Progress) -> list[Event]:
    allowed = []
    for event in Event:
        try:
            apply(p, event, is_correct=False, confirmed=True)
        except TransitionError:
            continue
        allowed.append(event)
    return allowed
