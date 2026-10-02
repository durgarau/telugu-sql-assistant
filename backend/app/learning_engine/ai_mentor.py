from app.ai.base import AIProvider
from app.database.models import Question
from app.prompts.mentor_prompts import AI_STATES, Material, build_messages

from .machine import REVEAL_STATES, Progress
from .states import State


def material_for(
    p: Progress,
    q: Question,
    *,
    student_sql: str | None = None,
    facts: tuple[str, ...] = (),
    already_said: tuple[str, ...] = (),
) -> Material:
    """Only what the learner has been shown, or is being shown in this turn."""
    level = p.hint_level
    return Material(
        prompt_text=q.prompt_text,
        concepts=tuple(q.concepts) if level >= 1 else None,
        structure_hint=q.structure_hint if level >= 2 else None,
        strong_hint=q.strong_hint if level >= 3 else None,
        solution_sql=q.correct_sql if p.state in REVEAL_STATES else None,
        student_sql=student_sql,
        facts=facts,
        failed_attempts=p.failed_attempts,
        already_said=already_said,
    )


def handles(state: State) -> bool:
    return state in AI_STATES


def generate(provider: AIProvider, p: Progress, m: Material) -> str:
    text = provider.complete(build_messages(p.state, m))
    if p.state is State.STRUCTURAL_HINT:
        text = f"```sql\n{m.structure_hint}\n```\n\n{text}"
    return text
