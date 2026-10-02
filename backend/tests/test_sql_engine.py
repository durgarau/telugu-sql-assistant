import json

import pytest

from app.config import Settings
from app.learning_engine.guard import leaks_solution
from app.sql_engine import mistakes as m
from app.sql_engine.evaluator import Verdict, evaluate
from app.sql_engine.sandbox import QueryError, run_query

QUESTIONS = json.loads(Settings().questions_path.read_text(encoding="utf-8"))
BY_ID = {q["id"]: q for q in QUESTIONS}
WHERE = BY_ID["where-cancelled-orders"]["correct_sql"]
TOP5 = BY_ID["order-by-top-5-amount"]["correct_sql"]
GROUP = BY_ID["group-by-city-order-count"]["correct_sql"]


# ---- sandbox: the security boundary -----------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE orders",
        "DELETE FROM orders",
        "UPDATE orders SET amount = 0",
        "INSERT INTO orders VALUES (99, 1, 'x', 'y', 1, 'UPI', '2026-01-01')",
        "CREATE TABLE t (x)",
        "ALTER TABLE orders ADD COLUMN z",
        "PRAGMA table_info(orders)",
        "VACUUM",
        "REINDEX",
        "BEGIN",
        "SELECT 1; DROP TABLE orders",
        "SELECT load_extension('evil')",
    ],
)
def test_sandbox_refuses_anything_but_reads(sql):
    with pytest.raises(QueryError) as e:
        run_query(sql)
    assert e.value.kind == "not_allowed", e.value.message


def test_sandbox_cannot_attach_or_create_files(tmp_path):
    target = tmp_path / "escape.db"
    with pytest.raises(QueryError) as e:
        run_query(f"ATTACH DATABASE '{target.as_posix()}' AS e")
    assert e.value.kind == "not_allowed"
    assert not target.exists()


def test_sandbox_data_cannot_change_between_queries():
    with pytest.raises(QueryError):
        run_query("DELETE FROM orders")
    assert run_query("SELECT COUNT(*) FROM orders").rows == [(22,)]


def test_sandbox_stops_runaway_queries():
    sql = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c"
    with pytest.raises(QueryError) as e:
        run_query(sql, timeout_s=0.3)
    assert e.value.kind == "timeout"


def test_sandbox_caps_rows():
    r = run_query("SELECT a.order_id FROM orders a, orders b, orders c", max_rows=100)
    assert len(r.rows) == 100 and r.truncated


def test_practice_amounts_are_distinct_so_top_n_has_no_ties():
    assert run_query("SELECT COUNT(DISTINCT amount) = COUNT(*) FROM orders").rows == [(1,)]


# ---- question bank integrity -------------------------------------------------


@pytest.mark.parametrize("q", QUESTIONS, ids=lambda q: q["id"])
def test_every_reference_query_runs_and_passes_itself(q):
    assert run_query(q["correct_sql"]).rows
    assert evaluate(q["correct_sql"], q["correct_sql"]).verdict is Verdict.CORRECT


# ---- evaluator verdicts --------------------------------------------------------


@pytest.mark.parametrize(
    ("ref", "sql", "verdict", "tags"),
    [
        # equivalent but differently written queries are correct
        (WHERE, "select * from orders where status='cancelled';", Verdict.CORRECT, []),
        (WHERE, "SELECT o.* FROM orders AS o WHERE o.status IN ('cancelled')", Verdict.CORRECT, []),
        (
            GROUP,
            "select city, count(order_id) as TOTAL_ORDERS from orders group by 1",
            Verdict.CORRECT,
            [],
        ),
        (
            TOP5,
            "SELECT order_id, amount FROM (SELECT * FROM orders) ORDER BY amount DESC LIMIT 5",
            Verdict.CORRECT,
            [],
        ),
        # mistakes
        (
            WHERE,
            "SELECT * FROM orders WHERE status = cancelled",
            Verdict.RUNTIME_ERROR,
            [m.MISSING_QUOTES],
        ),
        (
            WHERE,
            "SELECT * FROM orders WHERE status IN ('cancelled' OR 'returned')",
            Verdict.WRONG_RESULT,
            [m.IN_WITH_OR],
        ),
        (
            WHERE,
            "SELECT * FROM orders WHERE payment_method = NULL",
            Verdict.WRONG_RESULT,
            [m.NULL_COMPARISON],
        ),
        (WHERE, "SELECT * FORM orders", Verdict.SYNTAX_ERROR, []),
        (WHERE, "SELECT * FROM orders WHERE status = 'Cancelled'", Verdict.WRONG_RESULT, []),
        (
            TOP5,
            "SELECT order_id, amount FROM orders ORDER BY amount LIMIT 5",
            Verdict.WRONG_RESULT,
            [m.ORDER_DIRECTION],
        ),
        (
            TOP5,
            "SELECT order_id, amount FROM orders ORDER BY amount DESC",
            Verdict.WRONG_RESULT,
            [m.MISSING_LIMIT],
        ),
        (
            TOP5,
            "SELECT order_id, amount FROM orders ORDER BY amount DESC LIMIT 3",
            Verdict.WRONG_RESULT,
            [m.LIMIT_VALUE],
        ),
        (
            TOP5,
            "SELECT order_id, amount FROM orders LIMIT 5",
            Verdict.WRONG_RESULT,
            [m.MISSING_ORDER_BY],
        ),
        (
            TOP5,
            "SELECT amount, order_id FROM orders ORDER BY amount DESC LIMIT 5",
            Verdict.WRONG_RESULT,
            [],
        ),
        (
            GROUP,
            "SELECT city, COUNT(*) AS total_orders FROM orders",
            Verdict.WRONG_RESULT,
            [m.MISSING_GROUP_BY],
        ),
        (GROUP, "SELECT city, COUNT(*) FROM orders GROUP BY city", Verdict.WRONG_RESULT, []),
        (
            GROUP,
            "SELECT city, COUNT(*) AS total_orders FROM orders WHERE COUNT(*) > 1 GROUP BY city",
            Verdict.RUNTIME_ERROR,
            [m.AGGREGATE_IN_WHERE],
        ),
        (WHERE, "DROP TABLE orders", Verdict.NOT_ALLOWED, []),
        (WHERE, "SELECT 1; DELETE FROM orders", Verdict.NOT_ALLOWED, []),
    ],
)
def test_evaluator_verdicts(ref, sql, verdict, tags):
    e = evaluate(sql, ref)
    assert e.verdict is verdict, e.facts
    assert e.mistakes == tags
    if verdict is not Verdict.CORRECT:
        assert e.facts


def test_right_rows_in_wrong_order_fail_only_when_order_matters():
    reordered = (
        "SELECT order_id, amount FROM (SELECT order_id, amount FROM orders "
        "ORDER BY amount DESC LIMIT 5) ORDER BY order_id"
    )
    e = evaluate(reordered, TOP5)
    assert e.verdict is Verdict.WRONG_RESULT
    assert any("ORDER BY check" in f for f in e.facts)

    unordered_ref = "SELECT order_id FROM orders WHERE status = 'cancelled'"
    sql = "SELECT order_id FROM orders WHERE status = 'cancelled' ORDER BY order_id DESC"
    assert evaluate(sql, unordered_ref).verdict is Verdict.CORRECT


def test_column_order_gets_one_clear_fact():
    e = evaluate("SELECT amount, order_id FROM orders ORDER BY amount DESC LIMIT 5", TOP5)
    assert len(e.facts) == 1 and "order వేరుగా" in e.facts[0]


def test_specific_mistake_replaces_generic_row_advice():
    e = evaluate("SELECT order_id, amount FROM orders ORDER BY amount DESC LIMIT 3", TOP5)
    assert not any("strict" in f for f in e.facts)


WRONG_ATTEMPTS = {
    "select-customer-name-city": ["SELECT name FROM customers", "SELECT * FROM customers"],
    "where-cancelled-orders": [
        "SELECT * FROM orders WHERE status = cancelled",
        "SELECT * FROM orders WHERE status = 'Cancelled'",
        "SELECT * FROM orders",
    ],
    "where-delivered-orders": ["SELECT order_id, amount FROM orders"],
    "order-by-top-5-amount": [
        "SELECT order_id, amount FROM orders ORDER BY amount LIMIT 5",
        "SELECT order_id, amount FROM orders LIMIT 5",
    ],
    "group-by-city-order-count": [
        "SELECT city, COUNT(*) FROM orders",
        "SELECT COUNT(*) AS total_orders FROM orders",
    ],
}


@pytest.mark.parametrize(
    ("qid", "sql"), [(qid, s) for qid, sqls in WRONG_ATTEMPTS.items() for s in sqls]
)
def test_checker_facts_never_reveal_the_answer(qid, sql):
    q = BY_ID[qid]
    e = evaluate(sql, q["correct_sql"])
    assert e.verdict is not Verdict.CORRECT
    text = "\n".join(e.facts)
    assert not leaks_solution(text, q["correct_sql"], q["structure_hint"], [sql])
