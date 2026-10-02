"""A learner's progress, derived entirely from attempts and attempt_events.

A question counts as solved when it was solved without viewing the solution.
If a learner tried a question several times, the best outcome counts."""

from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Attempt, AttemptEvent, Question
from app.sql_engine import mistakes

from .machine import Progress
from .states import Event, Outcome, State
from .tutor import curriculum_order

_RANK = {Outcome.INDEPENDENT: 3, Outcome.WITH_HINTS: 2, Outcome.NEEDED_SOLUTION: 1}
WEAK_BELOW_PERCENT = 50


@dataclass
class TopicProgress:
    topic: str
    total: int
    attempted: int = 0
    solved: int = 0
    needed_solution: int = 0

    @property
    def mastery_percent(self) -> int:
        return round(100 * self.solved / self.total) if self.total else 0


@dataclass
class LearnerProgress:
    total_questions: int
    attempted: int = 0
    solved_independently: int = 0
    solved_with_hints: int = 0
    needed_solution: int = 0
    submissions: int = 0
    correct_submissions: int = 0
    topics: list[TopicProgress] = field(default_factory=list)
    mistakes: list[tuple[str, int]] = field(default_factory=list)
    question_outcomes: dict[str, str] = field(default_factory=dict)

    @property
    def overall_percent(self) -> int:
        solved = self.solved_independently + self.solved_with_hints
        return round(100 * solved / self.total_questions) if self.total_questions else 0

    @property
    def accuracy_percent(self) -> int | None:
        if not self.submissions:
            return None
        return round(100 * self.correct_submissions / self.submissions)

    @property
    def weak_topics(self) -> list[str]:
        return [
            t.topic
            for t in self.topics
            if t.attempted and (t.needed_solution or t.mastery_percent < WEAK_BELOW_PERCENT)
        ]

    @property
    def strong_topics(self) -> list[str]:
        return [t.topic for t in self.topics if t.mastery_percent == 100]


def _outcome(a: Attempt) -> Outcome | None:
    return Progress(
        state=State(a.state),
        hint_level=a.hint_level,
        failed_attempts=a.failed_attempts,
        solved=a.solved,
        saw_solution=a.saw_solution,
    ).outcome


def compute(db: Session, learner_id: str) -> LearnerProgress:
    questions = curriculum_order(list(db.scalars(select(Question))))
    attempts = db.scalars(select(Attempt).where(Attempt.learner_id == learner_id)).all()

    best: dict[str, Outcome | None] = {}
    for a in attempts:
        if not a.events:
            continue  # opened but never acted on (the UI opens a question on load)
        o = _outcome(a)
        prev = best.get(a.question_id)
        if a.question_id not in best or _RANK.get(o, 0) > _RANK.get(prev, 0):
            best[a.question_id] = o

    p = LearnerProgress(total_questions=len(questions), attempted=len(best))
    topics: dict[str, TopicProgress] = {}
    for q in questions:
        t = topics.setdefault(q.topic, TopicProgress(q.topic, 0))
        t.total += 1
        if q.id not in best:
            continue
        t.attempted += 1
        o = best[q.id]
        p.question_outcomes[q.id] = o.value if o else "in_progress"
        if o is Outcome.INDEPENDENT:
            p.solved_independently += 1
            t.solved += 1
        elif o is Outcome.WITH_HINTS:
            p.solved_with_hints += 1
            t.solved += 1
        elif o is Outcome.NEEDED_SOLUTION:
            p.needed_solution += 1
            t.needed_solution += 1
    p.topics = list(topics.values())

    submissions = db.scalars(
        select(AttemptEvent)
        .join(Attempt)
        .where(
            Attempt.learner_id == learner_id,
            AttemptEvent.event == Event.SUBMIT_ATTEMPT,
            AttemptEvent.verdict.is_not(None),
        )
    ).all()
    p.submissions = len(submissions)
    p.correct_submissions = sum(1 for e in submissions if e.is_correct)
    counts = Counter(tag for e in submissions for tag in (e.mistake_tags or []))
    p.mistakes = counts.most_common()
    return p


def label(tag: str) -> str:
    return mistakes.LABELS.get(tag, tag)
