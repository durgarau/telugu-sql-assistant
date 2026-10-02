from typing import Annotated, Any

from pydantic import BaseModel, Field, model_validator

from app.learning_engine.states import Event, Outcome, State
from app.sql_engine.error_catalog import MAX_ERROR_LENGTH
from app.sql_engine.evaluator import MAX_SQL_LENGTH, Verdict


class QuestionOut(BaseModel):
    """Never includes correct_sql or hints: those only leave via the tutor."""

    id: str
    topic: str
    difficulty: str
    prompt_text: str


class StartAttemptIn(BaseModel):
    learner_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    question_id: str = Field(min_length=1, max_length=80)


class EventIn(BaseModel):
    event: Event
    sql: str | None = Field(default=None, max_length=MAX_SQL_LENGTH)
    confirmed: bool = False

    @model_validator(mode="after")
    def _sql_only_on_submit(self) -> "EventIn":
        if self.event is not Event.SUBMIT_ATTEMPT and self.sql is not None:
            raise ValueError("sql is only accepted with SUBMIT_ATTEMPT")
        return self


class TurnOut(BaseModel):
    attempt_id: str
    question_id: str
    state: State
    hint_level: int
    failed_attempts: int
    outcome: Outcome | None
    allowed_events: list[Event]
    solution_needs_confirmation: bool
    mentor_message: str
    suggested_question_id: str | None = None
    evaluation: "EvaluationOut | None" = None


class EvaluationOut(BaseModel):
    """The learner's own result, so they can see what their query returned.
    The expected result is never sent: that would give the answer away."""

    verdict: Verdict
    mistakes: list[str]
    error: str | None
    columns: list[str] = []
    rows: list[list[Any]] = []
    total_rows_shown: int = 0
    truncated: bool = False


class ColumnOut(BaseModel):
    name: str
    type: str


class TableOut(BaseModel):
    name: str
    columns: list[ColumnOut]
    sample_rows: list[list[Any]]
    row_count: int


LearnerId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]


class ExplainErrorIn(BaseModel):
    error: str = Field(min_length=1, max_length=MAX_ERROR_LENGTH)
    sql: str | None = Field(default=None, max_length=MAX_SQL_LENGTH)
    attempt_id: str | None = Field(default=None, max_length=32)


class ExplainErrorOut(BaseModel):
    category: str
    dialect: str | None
    dialect_name: str | None
    token: str | None
    message: str
    source: str


class TopicProgressOut(BaseModel):
    topic: str
    total: int
    attempted: int
    solved: int
    needed_solution: int
    mastery_percent: int


class MistakeCountOut(BaseModel):
    tag: str
    label: str
    count: int


class ProgressOut(BaseModel):
    overall_percent: int
    total_questions: int
    attempted: int
    solved_independently: int
    solved_with_hints: int
    needed_solution: int
    submissions: int
    accuracy_percent: int | None
    topics: list[TopicProgressOut]
    mistakes: list[MistakeCountOut]
    weak_topics: list[str]
    strong_topics: list[str]
    question_outcomes: dict[str, str]


class ErrorOut(BaseModel):
    code: str
    message: str
