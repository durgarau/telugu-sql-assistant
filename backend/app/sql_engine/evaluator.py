"""Decides whether a learner's query is correct, deterministically.

Correct = the learner's result set equals the reference query's result set on
the practice DB (same columns, same rows; row order only matters when the
reference has ORDER BY). The LLM never decides correctness; it only explains
the facts produced here."""

import re
from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cache

import sqlglot
from sqlglot import exp

from . import mistakes
from .sandbox import QueryError, QueryResult, run_query

MAX_SQL_LENGTH = 5000
FLOAT_PLACES = 6


class Verdict(StrEnum):
    CORRECT = "correct"
    WRONG_RESULT = "wrong_result"
    SYNTAX_ERROR = "syntax_error"
    RUNTIME_ERROR = "runtime_error"
    NOT_ALLOWED = "not_allowed"


@dataclass
class Evaluation:
    verdict: Verdict
    facts: list[str] = field(default_factory=list)
    mistakes: list[str] = field(default_factory=list)
    result: QueryResult | None = None
    error: str | None = None

    @property
    def is_correct(self) -> bool:
        return self.verdict is Verdict.CORRECT


def normalize_sql(sql: str) -> str:
    s = sql.strip().rstrip(";").lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*([,()=<>])\s*", r"\1", s)
    return s.strip()


def _parse(sql: str) -> tuple[exp.Expression | None, bool]:
    """Return (tree, parse_failed). Tree is None for parse failures and multi-statement input."""
    try:
        trees = [t for t in sqlglot.parse(sql, read="sqlite") if t is not None]
    except sqlglot.errors.SqlglotError:
        return None, True
    return (trees[0] if len(trees) == 1 else None), False


def _not_allowed(message: str) -> Evaluation:
    return Evaluation(
        Verdict.NOT_ALLOWED,
        error=message,
        facts=["Practice లో SELECT (or WITH ... SELECT) queries మాత్రమే run చేయగలం."],
    )


def _norm_rows(rows: list[tuple]) -> list[tuple]:
    return [tuple(round(v, FLOAT_PLACES) if isinstance(v, float) else v for v in r) for r in rows]


@cache
def _reference(reference_sql: str) -> tuple[exp.Expression, QueryResult]:
    tree, _ = _parse(reference_sql)
    if tree is None:
        raise ValueError(f"reference query does not parse: {reference_sql!r}")
    return tree, run_query(reference_sql)


@dataclass
class _Diff:
    facts: list[str] = field(default_factory=list)
    advice: list[str] = field(default_factory=list)  # only shown when no mistake tag explains it

    def __bool__(self) -> bool:
        return bool(self.facts)


def _compare(got: QueryResult, want: QueryResult, ordered: bool) -> _Diff:
    d = _Diff()
    g_cols = [c.lower() for c in got.columns]
    w_cols = [c.lower() for c in want.columns]
    if len(g_cols) != len(w_cols):
        d.facts.append(
            f"మీ query {len(g_cols)} column(s) ఇచ్చింది, question కి {len(w_cols)} column(s) కావాలి."
        )
        return d
    if g_cols != w_cols and sorted(g_cols) == sorted(w_cols):
        d.facts.append("Columns correct, కానీ వాటి order వేరుగా ఉంది. Question అడిగిన order లో రాయండి.")
        return d
    for i, (g, w) in enumerate(zip(g_cols, w_cols, strict=True), start=1):
        if g != w:
            d.facts.append(
                f"Column {i} పేరు `{got.columns[i - 1]}` గా వస్తోంది. "
                "Question అడిగిన column / alias పేరు check చేయండి."
            )

    g_rows, w_rows = _norm_rows(got.rows), _norm_rows(want.rows)
    if len(g_rows) != len(w_rows):
        d.facts.append(f"మీ query {len(g_rows)} row(s) ఇచ్చింది, expected {len(w_rows)} row(s).")
        d.advice.append(
            "Extra rows వస్తున్నాయి: filter (WHERE) లేదా LIMIT check చేయండి."
            if len(g_rows) > len(w_rows)
            else "కొన్ని rows miss అవుతున్నాయి: filter condition ఎక్కువ strict గా ఉందేమో చూడండి."
        )
    elif Counter(g_rows) != Counter(w_rows):
        d.facts.append("Rows సంఖ్య సరిపోయింది, కానీ values వేరుగా ఉన్నాయి.")
    elif ordered and g_rows != w_rows:
        d.facts.append("Rows అన్నీ correct, కానీ order వేరుగా ఉంది. ORDER BY check చేయండి.")
    return d


def evaluate(student_sql: str, reference_sql: str) -> Evaluation:
    ref_tree, want = _reference(reference_sql)
    tree, parse_failed = _parse(student_sql)

    if tree is not None and not isinstance(tree, exp.Query):
        return _not_allowed(f"`{tree.key.upper()}` statements are not allowed here.")

    try:
        got = run_query(student_sql)
    except QueryError as e:
        if e.kind == "not_allowed":
            return _not_allowed(e.message)
        tags = mistakes.from_tree(tree) if tree is not None else []
        tags += mistakes.from_runtime_error(e.message)
        # SQLite's own message is shown (it points at the right token, and it is
        # what learners will meet in real databases); sqlglot only sets the verdict.
        is_syntax = parse_failed or "syntax error" in e.message
        return Evaluation(
            Verdict.SYNTAX_ERROR if is_syntax else Verdict.RUNTIME_ERROR,
            facts=[f"Query run అవ్వలేదు. Database error: `{e.message}`"]
            + mistakes.facts_for(tags, e.message),
            mistakes=tags,
            error=e.message,
        )

    ordered = ref_tree.args.get("order") is not None
    diff = _compare(got, want, ordered)
    tags = mistakes.from_tree(tree) if tree is not None else []
    if not diff:
        return Evaluation(Verdict.CORRECT, result=got, mistakes=tags)

    if tree is not None:
        tags += mistakes.against_reference(tree, ref_tree)
    return Evaluation(
        Verdict.WRONG_RESULT,
        facts=diff.facts + (mistakes.facts_for(tags) if tags else diff.advice),
        mistakes=tags,
        result=got,
    )
