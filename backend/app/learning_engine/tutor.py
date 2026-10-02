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
CURRICULUM = ["SELECT", "WHERE", "ORDER BY", "Aggregates", "GROUP BY", "HAVING"]
DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}
SOURCE_AI = "ai"
SOURCE_CANNED = "canned"
SOURCE_FALLBACK = "fallback"


@dataclass
class Turn:
    attempt: Attempt
    progress: Progress
    mentor_message: str
    suggested_question_id: str | None = None
    evaluation: evaluator.Evaluation | None = None


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


@dataclass(frozen=True)
class TurnContext:
    student_sql: str | None = None  # the query this turn is about
    learner_sql: tuple[str, ...] = ()  # everything the learner has typed so far
    facts: tuple[str, ...] = ()  # verified checker findings
    already_said: tuple[str, ...] = ()


def _leaks(p: Progress, q: Question, text: str, ctx: TurnContext) -> bool:
    return p.state not in machine.REVEAL_STATES and leaks_solution(
        text, q.correct_sql, q.structure_hint, ctx.learner_sql
    )


def message_for(
    p: Progress,
    q: Question,
    ctx: TurnContext = TurnContext(),
    *,
    provider: AIProvider | None = None,
) -> tuple[str, str]:
    """Return (message, source). AI first; canned on failure or leak; never an answer."""
    if provider is not None and ai_mentor.handles(p.state):
        m = ai_mentor.material_for(
            p, q, student_sql=ctx.student_sql, facts=ctx.facts, already_said=ctx.already_said
        )
        try:
            text = ai_mentor.generate(provider, p, m)
        except AIProviderError as e:
            log.warning("AI mentor failed (%s): question=%s state=%s", e, q.id, p.state)
        else:
            if not _leaks(p, q, text, ctx):
                return text, SOURCE_AI
            log.warning("AI solution leak blocked: question=%s state=%s", q.id, p.state)

    text = mentor.compose(p, _content(q), facts=ctx.facts)
    if _leaks(p, q, text, ctx):
        log.error("canned solution leak blocked: question=%s state=%s", q.id, p.state)
        return mentor.SAFE_FALLBACK, SOURCE_FALLBACK
    return text, SOURCE_CANNED


def topic_rank(topic: str) -> int:
    return CURRICULUM.index(topic) if topic in CURRICULUM else len(CURRICULUM)


def curriculum_order(questions: list[Question]) -> list[Question]:
    return sorted(
        questions, key=lambda q: (topic_rank(q.topic), DIFFICULTY_ORDER.get(q.difficulty, 3), q.id)
    )


def _suggest_next(db: Session, q: Question) -> str | None:
    """Same topic first, then same difficulty, then onward through the curriculum."""
    here = topic_rank(q.topic)
    candidates = db.scalars(select(Question).where(Question.id != q.id)).all()
    best = min(
        candidates,
        key=lambda c: (
            c.topic != q.topic,
            c.difficulty != q.difficulty,
            topic_rank(c.topic) < here,
            abs(topic_rank(c.topic) - here),
            c.id,
        ),
        default=None,
    )
    return best.id if best else None


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
    submitted = [e.submitted_sql for e in attempt.events if e.submitted_sql]

    evaluation: evaluator.Evaluation | None = None
    if event is Event.SUBMIT_ATTEMPT:
        if not sql or not sql.strip():
            raise machine.TransitionError("sql_required", "Submit చేయడానికి ముందు query రాయండి.")
        if before.state in machine.WORKING_STATES:
            evaluation = evaluator.evaluate(sql, q.correct_sql)
            if evaluation.verdict is evaluator.Verdict.NOT_ALLOWED:
                raise machine.TransitionError(
                    "query_not_allowed",
                    "Practice లో SELECT queries మాత్రమే run చేయగలం. "
                    "Data మార్చే commands (DROP, DELETE, UPDATE ...) ఇక్కడ allowed కాదు.",
                )
        submitted.append(sql)

    is_correct = evaluation.is_correct if evaluation else None
    if event is Event.SUBMIT_ATTEMPT and evaluation is None:
        is_correct = False  # state does not accept submissions; apply() will reject it
    after = machine.apply(before, event, is_correct=is_correct, confirmed=confirmed)

    ctx = TurnContext(
        student_sql=submitted[-1] if submitted else None,
        learner_sql=tuple(submitted),
        facts=tuple(evaluation.facts) if evaluation else (),
        already_said=tuple(e.mentor_message for e in attempt.events[-HISTORY_TURNS:]),
    )
    message, source = message_for(after, q, ctx, provider=provider)

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
            verdict=evaluation.verdict if evaluation else None,
            mistake_tags=evaluation.mistakes if evaluation else None,
            mentor_message=message,
            mentor_source=source,
        )
    )
    db.commit()

    suggested = _suggest_next(db, q) if after.state is State.SIMILAR_PRACTICE else None
    return Turn(attempt, after, message, suggested, evaluation)
