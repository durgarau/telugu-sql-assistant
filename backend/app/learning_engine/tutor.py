import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.base import AIProvider, AIProviderError
from app.database.models import Attempt, AttemptEvent, Question
from app.sql_engine import evaluator

from . import ai_mentor, machine, mentor
from .guard import leaks_solution
from .machine import Progress
from .states import Event, State

log = logging.getLogger(__name__)

HISTORY_TURNS = 3
SOURCE_AI = "ai"
SOURCE_CANNED = "canned"
SOURCE_FALLBACK = "fallback"


@dataclass
class Turn:
    attempt: Attempt
    progress: Progress
    mentor_message: str
    suggested_question_id: str | None = None


def progress_of(a: Attempt) -> Progress:
    return Progress(
        state=State(a.state),
        hint_level=a.hint_level,
        failed_attempts=a.failed_attempts,
        solved=a.solved,
        saw_solution=a.saw_solution,
    )


def _content(q: Question) -> mentor.QuestionContent:
    return mentor.QuestionContent(
        id=q.id,
        prompt_text=q.prompt_text,
        concepts=list(q.concepts),
        structure_hint=q.structure_hint,
        strong_hint=q.strong_hint,
        correct_sql=q.correct_sql,
    )


def _leaks(p: Progress, q: Question, text: str) -> bool:
    return p.state not in machine.REVEAL_STATES and leaks_solution(
        text, q.correct_sql, q.structure_hint
    )


def message_for(
    p: Progress,
    q: Question,
    *,
    provider: AIProvider | None = None,
    student_sql: str | None = None,
    already_said: tuple[str, ...] = (),
) -> tuple[str, str]:
    """Return (message, source). AI first; canned on failure or leak; never an answer."""
    if provider is not None and ai_mentor.handles(p.state):
        m = ai_mentor.material_for(p, q, student_sql=student_sql, already_said=already_said)
        try:
            text = ai_mentor.generate(provider, p, m)
        except AIProviderError as e:
            log.warning("AI mentor failed (%s): question=%s state=%s", e, q.id, p.state)
        else:
            if not _leaks(p, q, text):
                return text, SOURCE_AI
            log.warning("AI solution leak blocked: question=%s state=%s", q.id, p.state)

    text = mentor.compose(p, _content(q))
    if _leaks(p, q, text):
        log.error("canned solution leak blocked: question=%s state=%s", q.id, p.state)
        return mentor.SAFE_FALLBACK, SOURCE_FALLBACK
    return text, SOURCE_CANNED


def _suggest_next(db: Session, q: Question) -> str | None:
    same_topic = db.scalar(
        select(Question.id)
        .where(Question.topic == q.topic, Question.id != q.id)
        .order_by(Question.id)
    )
    return same_topic or db.scalar(
        select(Question.id).where(Question.id != q.id).order_by(Question.id)
    )


def start_attempt(db: Session, learner_id: str, question: Question) -> Turn:
    attempt = Attempt(
        learner_id=learner_id,
        question_id=question.id,
        state=State.QUESTION_RECEIVED,
    )
    db.add(attempt)
    db.commit()
    p = progress_of(attempt)
    message, _ = message_for(p, question)
    return Turn(attempt, p, message)


def _last_submitted_sql(attempt: Attempt) -> str | None:
    return next((e.submitted_sql for e in reversed(attempt.events) if e.submitted_sql), None)


def handle_event(
    db: Session,
    attempt: Attempt,
    event: Event,
    *,
    sql: str | None = None,
    confirmed: bool = False,
    provider: AIProvider | None = None,
) -> Turn:
    q = attempt.question
    before = progress_of(attempt)

    is_correct = None
    if event is Event.SUBMIT_ATTEMPT:
        if not sql or not sql.strip():
            raise machine.TransitionError("sql_required", "Submit చేయడానికి ముందు query రాయండి.")
        is_correct = evaluator.is_correct(sql, q.correct_sql)

    after = machine.apply(before, event, is_correct=is_correct, confirmed=confirmed)
    already_said = tuple(e.mentor_message for e in attempt.events[-HISTORY_TURNS:])
    message, source = message_for(
        after,
        q,
        provider=provider,
        student_sql=sql if event is Event.SUBMIT_ATTEMPT else _last_submitted_sql(attempt),
        already_said=already_said,
    )

    attempt.state = after.state
    attempt.hint_level = after.hint_level
    attempt.failed_attempts = after.failed_attempts
    attempt.solved = after.solved
    attempt.saw_solution = after.saw_solution
    db.add(
        AttemptEvent(
            attempt_id=attempt.id,
            event=event,
            from_state=before.state,
            to_state=after.state,
            submitted_sql=sql if event is Event.SUBMIT_ATTEMPT else None,
            is_correct=is_correct,
            mentor_message=message,
            mentor_source=source,
        )
    )
    db.commit()

    suggested = _suggest_next(db, q) if after.state is State.SIMILAR_PRACTICE else None
    return Turn(attempt, after, message, suggested)
