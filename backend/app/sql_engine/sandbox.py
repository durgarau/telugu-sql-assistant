"""Read-only execution of learner SQL.

Each query gets a fresh in-memory SQLite DB loaded from data/practice.sql, so
nothing a learner does can persist. On top of that, a SQLite authorizer allows
only reads, `query_only` is on, a progress handler enforces a time limit, and
results are capped. sqlglot checks in the evaluator only exist to give friendly
messages; this module is the actual security boundary."""

import sqlite3
import time
from dataclasses import dataclass
from functools import cache
from pathlib import Path

PRACTICE_SQL = Path(__file__).resolve().parents[3] / "data" / "practice.sql"
DEFAULT_TIMEOUT_S = 2.0
DEFAULT_MAX_ROWS = 1000
_PROGRESS_EVERY_N_OPS = 10_000

_ALLOWED_ACTIONS = frozenset(
    {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
        getattr(sqlite3, "SQLITE_RECURSIVE", 33),
    }
)
_BLOCKED_FUNCTIONS = frozenset({"load_extension", "readfile", "writefile", "edit"})
_NOT_ALLOWED_MARKERS = (
    "not authorized",
    "authorization denied",
    "readonly",
    "query_only",
    "one statement at a time",
)


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    truncated: bool


class QueryError(Exception):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind  # "error" | "timeout" | "not_allowed"
        self.message = message


@cache
def _script() -> str:
    return PRACTICE_SQL.read_text(encoding="utf-8")


def _authorizer(action, arg1, arg2, _db, _trigger):
    if action not in _ALLOWED_ACTIONS:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in _BLOCKED_FUNCTIONS:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(_script())
    conn.execute("PRAGMA query_only = ON")
    conn.set_authorizer(_authorizer)
    return conn


@dataclass(frozen=True)
class TableInfo:
    name: str
    columns: list[tuple[str, str]]  # (name, type)
    sample_rows: list[tuple]
    row_count: int


@cache
def practice_tables(sample_size: int = 3) -> tuple[TableInfo, ...]:
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(_script())
        names = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY rowid"
            )
        ]
        return tuple(
            TableInfo(
                name=t,
                columns=[(c[1], c[2]) for c in conn.execute(f"PRAGMA table_info({t})")],
                sample_rows=conn.execute(f"SELECT * FROM {t} LIMIT ?", (sample_size,)).fetchall(),
                row_count=conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0],
            )
            for t in names
        )
    finally:
        conn.close()


@cache
def schema_columns() -> frozenset[str]:
    tables = practice_tables()
    cols = {name.lower() for t in tables for name, _ in t.columns}
    return frozenset(cols) | frozenset(t.name.lower() for t in tables)


def run_query(
    sql: str, *, timeout_s: float = DEFAULT_TIMEOUT_S, max_rows: int = DEFAULT_MAX_ROWS
) -> QueryResult:
    conn = _connect()
    deadline = time.monotonic() + timeout_s
    conn.set_progress_handler(lambda: int(time.monotonic() > deadline), _PROGRESS_EVERY_N_OPS)
    try:
        cur = conn.execute(sql)
        if cur.description is None:
            raise QueryError("not_allowed", "Only queries that return rows are allowed.")
        rows = cur.fetchmany(max_rows + 1)
        columns = [d[0] for d in cur.description]
    except (sqlite3.DatabaseError, sqlite3.Warning) as e:
        msg = str(e)
        if time.monotonic() > deadline or msg == "interrupted":
            raise QueryError("timeout", f"Query {timeout_s:g} seconds లో పూర్తి కాలేదు.") from e
        if any(s in msg for s in _NOT_ALLOWED_MARKERS):
            raise QueryError("not_allowed", msg) from e
        raise QueryError("error", msg) from e
    finally:
        conn.close()
    return QueryResult(columns, rows[:max_rows], truncated=len(rows) > max_rows)
