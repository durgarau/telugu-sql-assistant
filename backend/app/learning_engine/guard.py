"""Last line of defence: blocks any mentor message that contains the full
solution while the learner is still working. Matters most once an LLM writes
the messages (M2), since prompt instructions alone are not a guarantee."""

from app.sql_engine.evaluator import normalize_sql


def leaks_solution(text: str, correct_sql: str) -> bool:
    return normalize_sql(correct_sql) in normalize_sql(text)
