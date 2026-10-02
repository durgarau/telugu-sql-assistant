from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Attempt, Question
from app.learning_engine import machine, tutor

from .schemas import ErrorOut, EventIn, QuestionOut, StartAttemptIn, TurnOut

router = APIRouter()


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
    )


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
    last = a.events[-1].mentor_message if a.events else tutor.message_for(p, a.question)
    return _turn_out(tutor.Turn(a, p, last))


@router.post(
    "/attempts/{attempt_id}/events",
    response_model=TurnOut,
    responses={409: {"model": ErrorOut}, 422: {"model": ErrorOut}},
)
def post_event(attempt_id: str, body: EventIn, db: Session = Depends(get_db)) -> TurnOut:
    a = db.get(Attempt, attempt_id)
    if a is None:
        raise HTTPException(404, "attempt not found")
    try:
        turn = tutor.handle_event(db, a, body.event, sql=body.sql, confirmed=body.confirmed)
    except machine.TransitionError as e:
        status = 422 if e.code == "sql_required" else 409
        raise HTTPException(status, {"code": e.code, "message": e.message}) from e
    return _turn_out(turn)
