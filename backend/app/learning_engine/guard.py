"""Last line of defence: blocks any mentor message that gives away the answer
while the learner is still working.

Hiding correct_sql from the LLM is not enough, since it can derive the answer
from the question itself. So besides the full query, every answer line the
learner still has to fill in (not already shown in the skeleton) is blocked.
Anything the learner has typed themselves is not a leak, so feedback can
quote the parts of their own query that are already right."""

import re
from collections.abc import Iterable

import sqlglot
from sqlglot import exp

from app.sql_engine.evaluator import normalize_sql

_CODE = re.compile(r"```(?:sql)?\s*(.*?)```|`([^`\n]+)`", re.IGNORECASE | re.DOTALL)


def rewrites_query(text: str, learner_sql: Iterable[str] = ()) -> bool:
    """True if the text contains a complete SELECT ... FROM query in code formatting
    that the learner did not write themselves, i.e. the mentor wrote it for them."""
    known = {normalize_sql(s) for s in learner_sql}
    for m in _CODE.finditer(text):
        snippet = (m.group(1) or m.group(2) or "").strip()
        # A skeleton with ____ blanks is a hint, not a finished query.
        if not snippet or "__" in snippet or normalize_sql(snippet) in known:
            continue
        try:
            trees = sqlglot.parse(snippet, read="sqlite")
        except sqlglot.errors.SqlglotError:
            continue
        for tree in trees:
            if isinstance(tree, exp.Query) and tree.find(exp.From):
                return True
    return False


_CONNECTOR = re.compile(r"^(?:and|or)\s+")


def hidden_lines(correct_sql: str, structure_hint: str) -> list[str]:
    shown = normalize_sql(structure_hint)
    # "AND x = 1" and "MAX(a) AS m," leak just as much without the AND or the comma.
    lines = (
        _CONNECTOR.sub("", normalize_sql(line)).rstrip(",").strip()
        for line in correct_sql.splitlines()
        if line.strip()
    )
    # FROM <table> usually just repeats the table named in the question.
    return [line for line in lines if line not in shown and not line.startswith("from ")]


def leaks_solution(
    text: str,
    correct_sql: str,
    structure_hint: str,
    learner_sql: Iterable[str] = (),
) -> bool:
    t = normalize_sql(text)
    known = [normalize_sql(s) for s in learner_sql]
    candidates = [normalize_sql(correct_sql), *hidden_lines(correct_sql, structure_hint)]
    return any(c in t and not any(c in k for k in known) for c in candidates)
