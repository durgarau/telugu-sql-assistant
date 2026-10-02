"""Last line of defence: blocks any mentor message that gives away the answer
while the learner is still working.

Hiding correct_sql from the LLM is not enough, since it can derive the answer
from the question itself. So besides the full query, every answer line the
learner still has to fill in (not already shown in the skeleton) is blocked."""

from app.sql_engine.evaluator import normalize_sql


def hidden_lines(correct_sql: str, structure_hint: str) -> list[str]:
    shown = normalize_sql(structure_hint)
    lines = (normalize_sql(line) for line in correct_sql.splitlines() if line.strip())
    # FROM <table> usually just repeats the table named in the question.
    return [line for line in lines if line not in shown and not line.startswith("from ")]


def leaks_solution(text: str, correct_sql: str, structure_hint: str) -> bool:
    t = normalize_sql(text)
    if normalize_sql(correct_sql) in t:
        return True
    return any(line in t for line in hidden_lines(correct_sql, structure_hint))
