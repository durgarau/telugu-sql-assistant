from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Attempt, Question
from app.learning_engine import machine, tutor
from app.sql_engine import evaluator

from .schemas import ErrorOut, EvaluationOut, EventIn, QuestionOut, StartAttemptIn, TurnOut

router = APIRouter()

PREVIEW_ROWS = 50
VALIDATION_CODES = frozenset({"sql_required", "query_not_allowed"})


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as db:
        yield db


def _turn_out(t: tutor.Turn) -> TurnOut:
    p = t.progress
    return TurnOut(
        attempt_id=t.attempt.id,
        question_id=t.attempt.question_id,
        state=p.state,
        hint_level=p.hint_level,
        failed_attempts=p.failed_attempts,
        outcome=p.outcome,
        allowed_events=machine.allowed_events(p),
        solution_needs_confirmation=p.solution_needs_confirmation,
        mentor_message=t.mentor_message,
        suggested_question_id=t.suggested_question_id,
        evaluation=_evaluation_out(t.evaluation) if t.evaluation else None,
    )


def _evaluation_out(e: evaluator.Evaluation) -> EvaluationOut:
    out = EvaluationOut(verdict=e.verdict, mistakes=e.mistakes, error=e.error)
    if e.result is not None:
        rows = e.result.rows[:PREVIEW_ROWS]
        out.columns = e.result.columns
        out.rows = [list(r) for r in rows]
        out.total_rows_shown = len(rows)
        out.truncated = e.result.truncated or len(e.result.rows) > PREVIEW_ROWS
    return out


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/questions", response_model=list[QuestionOut])
def list_questions(db: Session = Depends(get_db)) -> list[Question]:
    return list(db.scalars(select(Question).order_by(Question.topic, Question.id)))


@router.get("/questions/{question_id}", response_model=QuestionOut)
def get_question(question_id: str, db: Session = Depends(get_db)) -> Question:
    q = db.get(Question, question_id)
    if q is None:
        raise HTTPException(404, "question not found")
    return q


@router.post("/attempts", response_model=TurnOut, status_code=201)
def start_attempt(body: StartAttemptIn, db: Session = Depends(get_db)) -> TurnOut:
    q = db.get(Question, body.question_id)
    if q is None:
        raise HTTPException(404, "question not found")
    return _turn_out(tutor.start_attempt(db, body.learner_id, q))


@router.get("/attempts/{attempt_id}", response_model=TurnOut)
def get_attempt(attempt_id: str, db: Session = Depends(get_db)) -> TurnOut:
    a = db.get(Attempt, attempt_id)
    if a is None:
        raise HTTPException(404, "attempt not found")
    p = tutor.progress_of(a)
    last = a.events[-1].mentor_message if a.events else tutor.message_for(p, a.question)[0]
    return _turn_out(tutor.Turn(a, p, last))


@router.post(
    "/attempts/{attempt_id}/events",
    response_model=TurnOut,
    responses={409: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def post_event(
    attempt_id: str, body: EventIn, request: Request, db: Session = Depends(get_db)
) -> TurnOut:
    a = db.get(Attempt, attempt_id)
    if a is None:
        raise HTTPException(404, "attempt not found")
    try:
        turn = tutor.handle_event(
            db,
            a,
            body.event,
            sql=body.sql,
            confirmed=body.confirmed,
            provider=request.app.state.ai_provider,
        )
    except machine.TransitionError as e:
        status = 422 if e.code in VALIDATION_CODES else 409
        raise HTTPException(status, {"code": e.code, "message": e.message}) from e
    return _turn_out(turn)
