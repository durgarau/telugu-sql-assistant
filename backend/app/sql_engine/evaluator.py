"""Placeholder evaluator. M3 replaces is_correct with sqlglot parsing plus
result-set comparison against a read-only SQLite sandbox."""

import re

MAX_SQL_LENGTH = 5000


def normalize_sql(sql: str) -> str:
    s = sql.strip().rstrip(";").lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*([,()=<>])\s*", r"\1", s)
    return s.strip()


def is_correct(submitted: str, correct_sql: str) -> bool:
    return normalize_sql(submitted) == normalize_sql(correct_sql)
