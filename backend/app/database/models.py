import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    topic: Mapped[str] = mapped_column(String(40), index=True)
    difficulty: Mapped[str] = mapped_column(String(10))
    prompt_text: Mapped[str] = mapped_column(Text)
    concepts: Mapped[list[str]] = mapped_column(JSON)
    structure_hint: Mapped[str] = mapped_column(Text)
    strong_hint: Mapped[str] = mapped_column(Text)
    correct_sql: Mapped[str] = mapped_column(Text)


class Attempt(Base):
    """One learner working through one question."""

    __tablename__ = "attempts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    learner_id: Mapped[str] = mapped_column(String(64), index=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"))
    state: Mapped[str] = mapped_column(String(32))
    hint_level: Mapped[int] = mapped_column(default=0)
    failed_attempts: Mapped[int] = mapped_column(default=0)
    solved: Mapped[bool] = mapped_column(default=False)
    saw_solution: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)

    question: Mapped[Question] = relationship()
    events: Mapped[list["AttemptEvent"]] = relationship(
        back_populates="attempt", order_by="AttemptEvent.id"
    )


class AttemptEvent(Base):
    """Audit log of every transition: feeds progress and mistake tracking later."""

    __tablename__ = "attempt_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("attempts.id"), index=True)
    event: Mapped[str] = mapped_column(String(32))
    from_state: Mapped[str] = mapped_column(String(32))
    to_state: Mapped[str] = mapped_column(String(32))
    submitted_sql: Mapped[str | None] = mapped_column(Text)
    is_correct: Mapped[bool | None]
    mentor_message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    attempt: Mapped[Attempt] = relationship(back_populates="events")
