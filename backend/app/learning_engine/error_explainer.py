"""Explain Error: catalog match → (AI rephrasing) → guards → reviewed fallback.

Works standalone (an error pasted from MySQL/PostgreSQL/BigQuery) or inside a
practice attempt, where the question's leak guard also applies."""

import logging
from dataclasses import dataclass

from app.ai.base import AIProvider, AIProviderError
from app.database.models import Attempt
from app.prompts.mentor_prompts import build_error_messages
from app.sql_engine import error_catalog

from . import machine
from .guard import leaks_solution, rewrites_query
from .states import State

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Explanation:
    category: str
    dialect: str | None
    token: str | None
    message: str
    source: str  # "ai" | "catalog"


def explain(
    error: str,
    sql: str | None = None,
    *,
    attempt: Attempt | None = None,
    provider: AIProvider | None = None,
) -> Explanation:
    m = error_catalog.match(error)
    reviewed = error_catalog.explain(m)
    dialect = error_catalog.DIALECT_NAMES.get(m.dialect) if m.dialect else None

    if provider is not None:
        try:
            text = provider.complete(build_error_messages(error, sql, dialect, reviewed))
        except AIProviderError as e:
            log.warning("AI error explanation failed (%s)", e)
        else:
            if _safe(text, sql, attempt):
                return Explanation(m.category, m.dialect, m.token, text, "ai")
            log.warning("AI error explanation blocked: category=%s", m.category)
    return Explanation(m.category, m.dialect, m.token, reviewed, "catalog")


def _safe(text: str, sql: str | None, attempt: Attempt | None) -> bool:
    learner_sql = [e.submitted_sql for e in attempt.events if e.submitted_sql] if attempt else []
    if sql:
        learner_sql.append(sql)
    if rewrites_query(text, learner_sql):
        return False
    if attempt is not None and State(attempt.state) not in machine.REVEAL_STATES:
        q = attempt.question
        return not leaks_solution(text, q.correct_sql, q.structure_hint, learner_sql)
    return True
