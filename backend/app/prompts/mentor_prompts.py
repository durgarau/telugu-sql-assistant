"""Prompt templates for the AI mentor. See docs/PROMPT_DESIGN.md.

Templates only see a Material object, which the learning engine fills with
what the learner has already been shown. They cannot reach correct_sql
unless the engine is in a reveal state."""

from collections.abc import Callable
from dataclasses import dataclass

from app.ai.base import ChatMessage
from app.learning_engine.states import State

MAX_ECHO_CHARS = 600

SYSTEM_PROMPT = """\
You are "SQL Mitra", a patient SQL mentor for Telugu-speaking beginners.

LANGUAGE
- Write in natural spoken Telugu mixed with English, like a friendly Telugu senior \
explaining to a junior. Use Telugu script for Telugu words.
- Keep SQL keywords and technical terms in English: SELECT, WHERE, GROUP BY, HAVING, \
JOIN, table, column, row, query, filter, aggregate function, alias.
- Avoid formal or bookish Telugu. Short, clear sentences.
- Tone example: "ఈ question లో మనకు `GROUP BY` ఎందుకు కావాలో first understand చేద్దాం."

TEACHING RULES (never break these)
- You are teaching, not answering. Never write the complete SQL query.
- Never write a finished clause the learner still has to produce, such as the full \
WHERE condition, the GROUP BY column, the ORDER BY column with its direction, or the \
LIMIT number. Use ____ blanks or a guiding question instead.
- Use only the material in the context. Do not go beyond the current hint level.
- End with one clear next step or question for the learner.

FORMAT
- Markdown, at most about 120 words. Put SQL keywords and column names in `backticks`.
- No greetings, no emojis, no headings."""


@dataclass(frozen=True)
class Material:
    prompt_text: str
    concepts: tuple[str, ...] | None = None
    structure_hint: str | None = None
    strong_hint: str | None = None
    solution_sql: str | None = None
    student_sql: str | None = None
    failed_attempts: int = 0
    already_said: tuple[str, ...] = ()


def _clip(s: str) -> str:
    return s if len(s) <= MAX_ECHO_CHARS else s[:MAX_ECHO_CHARS] + " …"


def _need(value, name: str):
    if value is None:
        raise ValueError(f"material missing {name}")
    return value


def _explained(m: Material) -> str:
    return (
        "Explain what this question is asking. Cover: which output columns are needed, "
        "which table, and whether any filtering, calculation, sorting or limit is required. "
        "Do not show SQL syntax yet. End by asking the learner to think about the first step."
    )


def _concept(m: Material) -> str:
    concepts = ", ".join(_need(m.concepts, "concepts"))
    return (
        f"The concepts needed are: {concepts}. Explain briefly why each one is needed for "
        "this question (a tiny real-life analogy is fine). Then ask 2-3 guiding questions, "
        "e.g. 'ఈ filter కోసం ఏ clause ఉపయోగిస్తాం?'. Do not show a query skeleton."
    )


def _structural(m: Material) -> str:
    _need(m.structure_hint, "structure_hint")
    return (
        "The query skeleton above is shown to the learner automatically, so do not repeat "
        "it. Write one guiding question per ____ blank that helps them work out what goes "
        "there. Do not fill any blank."
    )


def _error(m: Material) -> str:
    sql = _need(m.student_sql, "student_sql")
    return (
        f"The learner submitted this query (attempt {m.failed_attempts}):\n"
        f"```sql\n{_clip(sql)}\n```\n"
        "The automatic checker says its result does not match the question. "
        "First say what is correct in their attempt. Then point to the most likely problem, "
        "explain why it is a problem, and how to think about fixing it. Show the location "
        "with a ____ blank instead of the fix. Ask them to try again."
    )


def _strong(m: Material) -> str:
    _need(m.strong_hint, "strong_hint")
    last = f"Their last query:\n```sql\n{_clip(m.student_sql)}\n```\n" if m.student_sql else ""
    return (
        f"The learner is stuck after {m.failed_attempts} failed attempt(s).\n{last}"
        "Give a more explicit clue, based on the teacher-written strong hint above. "
        "You may name the clause and the kind of value needed, but the final value or "
        "column must stay a ____ blank."
    )


def _explanation(m: Material) -> str:
    sql = _need(m.solution_sql, "solution_sql")
    return (
        "The learner has now seen the final query. Explain it line by line: for each line, "
        "what it does and why this question needs it. Then name one common beginner "
        "mistake for this kind of question. The 120-word limit does not apply here.\n"
        f"```sql\n{sql}\n```"
    )


TASKS: dict[State, Callable[[Material], str]] = {
    State.QUESTION_EXPLAINED: _explained,
    State.CONCEPT_HINT: _concept,
    State.STRUCTURAL_HINT: _structural,
    State.ERROR_ANALYSIS: _error,
    State.STRONG_HINT: _strong,
    State.EXPLANATION: _explanation,
}
AI_STATES = frozenset(TASKS)


def _context(m: Material) -> str:
    parts = [f"## Question\n{m.prompt_text}"]
    if m.concepts:
        parts.append("## Concepts the learner has seen\n" + ", ".join(m.concepts))
    if m.structure_hint:
        parts.append(f"## Query skeleton the learner has seen\n```sql\n{m.structure_hint}\n```")
    if m.strong_hint:
        parts.append(f"## Teacher-written strong hint\n{m.strong_hint}")
    if m.already_said:
        said = "\n".join(f"- {_clip(s)}" for s in m.already_said)
        parts.append(f"## You already told the learner (do not repeat)\n{said}")
    return "\n\n".join(parts)


def build_messages(state: State, m: Material) -> list[ChatMessage]:
    task = TASKS[state](m)
    return [
        ChatMessage("system", SYSTEM_PROMPT),
        ChatMessage("user", f"{_context(m)}\n\n## Your task\n{task}"),
    ]
