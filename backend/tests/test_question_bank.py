"""Quality bar for data/questions.json. A wrong reference answer or an ambiguous
prompt marks a correct learner wrong, so every question must pass these."""

import json
from collections import Counter

import pytest
import sqlglot
from sqlglot import exp

from app.config import Settings
from app.learning_engine.guard import hidden_lines, leaks_solution
from app.learning_engine.tutor import CURRICULUM
from app.sql_engine.evaluator import Verdict, evaluate
from app.sql_engine.sandbox import run_query

QUESTIONS = json.loads(Settings().questions_path.read_text(encoding="utf-8"))
FIELDS = {
    "id",
    "topic",
    "difficulty",
    "prompt_text",
    "concepts",
    "structure_hint",
    "strong_hint",
    "correct_sql",
}
ids = pytest.mark.parametrize("q", QUESTIONS, ids=lambda q: q["id"])


def test_ids_and_prompts_are_unique():
    assert len({q["id"] for q in QUESTIONS}) == len(QUESTIONS)
    assert len({q["prompt_text"] for q in QUESTIONS}) == len(QUESTIONS)


def test_every_topic_has_at_least_two_questions_so_similar_practice_stays_in_topic():
    counts = Counter(q["topic"] for q in QUESTIONS)
    assert set(counts) == set(CURRICULUM)
    assert all(n >= 2 for n in counts.values()), counts


@ids
def test_fields_are_complete(q):
    assert set(q) == FIELDS
    assert q["difficulty"] in {"easy", "medium", "hard"}
    assert q["concepts"] and all(isinstance(c, str) for c in q["concepts"])
    assert "____" in q["structure_hint"]
    assert q["strong_hint"].strip()


@ids
def test_reference_runs_returns_rows_and_passes_itself(q):
    assert run_query(q["correct_sql"]).rows
    assert evaluate(q["correct_sql"], q["correct_sql"]).verdict is Verdict.CORRECT


@ids
def test_prompt_names_every_output_column(q):
    """Column names are checked, so learners must be told what to call them."""
    tree = sqlglot.parse_one(q["correct_sql"], read="sqlite")
    if any(isinstance(p, exp.Star) for p in tree.expressions):
        return
    prompt = q["prompt_text"].lower()
    for col in run_query(q["correct_sql"]).columns:
        assert col.lower() in prompt, f"prompt never mentions output column {col!r}"


@ids
def test_sorted_results_have_no_ties(q):
    """With ties, a correct query that breaks them differently would be marked wrong."""
    tree = sqlglot.parse_one(q["correct_sql"], read="sqlite")
    order = tree.args.get("order")
    if order is None:
        return
    result = run_query(q["correct_sql"])
    cols = [c.lower() for c in result.columns]
    keys = []
    for o in order.expressions:
        name = o.this.alias_or_name.lower()
        assert name in cols, f"ORDER BY key {name!r} must be an output column"
        keys.append(cols.index(name))
    limit = tree.args.get("limit")
    unlimited = tree.copy()
    unlimited.set("limit", None)
    rows = run_query(unlimited.sql(dialect="sqlite")).rows
    compared = rows[: int(limit.expression.name) + 1] if limit is not None else rows
    tuples = [tuple(r[i] for i in keys) for r in compared]
    assert len(set(tuples)) == len(tuples), f"tied sort keys in {tuples}"


@ids
def test_hints_hide_the_answer(q):
    assert hidden_lines(q["correct_sql"], q["structure_hint"])
    for field in ("structure_hint", "strong_hint", "prompt_text"):
        assert not leaks_solution(q[field], q["correct_sql"], q["structure_hint"]), field


BY_ID = {q["id"]: q for q in QUESTIONS}

# Other correct ways a learner might write the answer. Each must be accepted.
EQUIVALENT_ANSWERS = [
    ("select-distinct-order-cities", "select city from orders group by city"),
    (
        "select-amount-with-gst",
        "SELECT order_id, amount, amount + amount * 0.18 AS amount_with_gst FROM orders",
    ),
    (
        "where-in-cities",
        "SELECT name, city FROM customers WHERE city = 'Hyderabad' "
        "OR city = 'Vijayawada' OR city = 'Visakhapatnam'",
    ),
    (
        "where-null-payment",
        "select o.order_id, o.status from orders o where o.payment_method is null",
    ),
    (
        "where-amount-between",
        "SELECT order_id, amount FROM orders WHERE amount >= 500 AND amount <= 1000",
    ),
    ("where-name-starts-with-s", "select customer_id, name from customers where name like 's%'"),
    (
        "where-delivered-upi-above-1000",
        "SELECT order_id, amount, payment_method FROM orders "
        "WHERE amount > 1000 AND payment_method = 'UPI' AND status = 'delivered'",
    ),
    ("order-by-recent-3", "SELECT order_id, order_date FROM orders ORDER BY 2 DESC LIMIT 3"),
    ("order-by-city-then-name", "SELECT name, city FROM customers ORDER BY city ASC, name ASC"),
    (
        "agg-order-stats",
        "SELECT COUNT(order_id) AS order_count, MAX(amount) AS max_amount, "
        "ROUND(AVG(amount), 2) AS avg_amount FROM orders",
    ),
    ("group-by-status-total", "select status, sum(amount) as total_amount from orders group by 1"),
    (
        "group-by-payment-method-ranked",
        "SELECT payment_method, COUNT(*) AS order_count FROM orders "
        "WHERE payment_method IS NOT NULL GROUP BY payment_method "
        "ORDER BY COUNT(*) DESC, payment_method ASC",
    ),
    (
        "having-cities-more-than-2-orders",
        "SELECT city, COUNT(*) AS order_count FROM orders GROUP BY city HAVING order_count > 2",
    ),
    (
        "having-big-spenders",
        "SELECT customer_id, SUM(amount) AS total_spent FROM orders "
        "WHERE status = 'delivered' GROUP BY customer_id HAVING total_spent > 5000",
    ),
]


@pytest.mark.parametrize(("qid", "sql"), EQUIVALENT_ANSWERS)
def test_equivalent_answers_are_accepted(qid, sql):
    e = evaluate(sql, BY_ID[qid]["correct_sql"])
    assert e.verdict is Verdict.CORRECT, e.facts


# Typical beginner mistakes: (question, attempt, expected mistake tag or None).
COMMON_MISTAKES = [
    ("select-distinct-order-cities", "SELECT city FROM orders", None),
    (
        "select-amount-with-gst",
        "SELECT order_id, amount, amount * 0.18 AS amount_with_gst FROM orders",
        None,
    ),
    (
        "where-in-cities",
        "SELECT name, city FROM customers WHERE city IN "
        "('Hyderabad' OR 'Vijayawada' OR 'Visakhapatnam')",
        "in_with_or",
    ),
    (
        "where-null-payment",
        "SELECT order_id, status FROM orders WHERE payment_method = NULL",
        "null_comparison",
    ),
    ("where-name-starts-with-s", "SELECT customer_id, name FROM customers WHERE name = 'S%'", None),
    (
        "where-delivered-upi-above-1000",
        "SELECT order_id, amount, payment_method FROM orders "
        "WHERE status = 'delivered' AND payment_method = UPI AND amount > 1000",
        "missing_quotes",
    ),
    (
        "order-by-recent-3",
        "SELECT order_id, order_date FROM orders ORDER BY order_date LIMIT 3",
        "order_direction",
    ),
    ("agg-delivered-revenue", "SELECT SUM(amount) AS total_revenue FROM orders", None),
    (
        "group-by-status-total",
        "SELECT status, SUM(amount) AS total_amount FROM orders",
        "missing_group_by",
    ),
    (
        "group-by-payment-method-ranked",
        "SELECT payment_method, COUNT(*) AS order_count FROM orders "
        "GROUP BY payment_method ORDER BY order_count DESC, payment_method",
        None,
    ),
    (
        "having-cities-more-than-2-orders",
        "SELECT city, COUNT(*) AS order_count FROM orders WHERE COUNT(*) > 2 GROUP BY city",
        "aggregate_in_where",
    ),
    (
        "having-big-spenders",
        "SELECT customer_id, SUM(amount) AS total_spent FROM orders "
        "GROUP BY customer_id HAVING SUM(amount) > 5000",
        None,
    ),
]


@pytest.mark.parametrize(("qid", "sql", "tag"), COMMON_MISTAKES)
def test_common_mistakes_get_specific_feedback_without_the_answer(qid, sql, tag):
    q = BY_ID[qid]
    e = evaluate(sql, q["correct_sql"])
    assert e.verdict is not Verdict.CORRECT
    assert e.facts
    if tag:
        assert tag in e.mistakes, (e.mistakes, e.facts)
    text = "\n".join(e.facts)
    assert not leaks_solution(text, q["correct_sql"], q["structure_hint"], [sql])


def test_bank_spans_all_three_levels():
    assert {q["difficulty"] for q in QUESTIONS} == {"easy", "medium", "hard"}
