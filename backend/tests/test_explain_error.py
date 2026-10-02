import pytest

from app.learning_engine import error_explainer
from app.learning_engine.guard import rewrites_query
from app.sql_engine import error_catalog as ec

from .helpers import FailingProvider, FakeProvider, event, start

# Real error messages, copied in the shape each database prints them.
ERRORS = [
    ('near "FORM": syntax error', ec.SYNTAX, "sqlite", "FORM"),
    ("no such column: cancelled", ec.NO_COLUMN, "sqlite", "cancelled"),
    ("no such table: order", ec.NO_TABLE, "sqlite", "order"),
    ("misuse of aggregate: COUNT()", ec.AGG_IN_WHERE, "sqlite", "COUNT"),
    ("ambiguous column name: city", ec.AMBIGUOUS, "sqlite", "city"),
    ('unrecognized token: "\'cancelled"', ec.UNCLOSED_STRING, "sqlite", "cancelled"),
    (
        "ERROR 1064 (42000): You have an error in your SQL syntax; check the manual that "
        "corresponds to your MySQL server version for the right syntax to use near "
        "'FORM orders WHERE status = 'x'' at line 1",
        ec.SYNTAX,
        "mysql",
        "FORM",
    ),
    (
        "ERROR 1054 (42S22): Unknown column 'cancelled' in 'where clause'",
        ec.NO_COLUMN,
        "mysql",
        "cancelled",
    ),
    ("ERROR 1146 (42S02): Table 'shop.order' doesn't exist", ec.NO_TABLE, "mysql", "shop.order"),
    ("ERROR 1111 (HY000): Invalid use of group function", ec.AGG_IN_WHERE, "mysql", None),
    (
        "ERROR 1055 (42000): Expression #1 of SELECT list is not in GROUP BY clause and contains "
        "nonaggregated column 'shop.orders.city' which is not functionally dependent on columns "
        "in GROUP BY clause; this is incompatible with sql_mode=only_full_group_by",
        ec.GROUP_BY,
        "mysql",
        "shop.orders.city",
    ),
    (
        'ERROR:  syntax error at or near "FORM"\nLINE 1: SELECT * FORM orders;',
        ec.SYNTAX,
        "postgresql",
        "FORM",
    ),
    ('ERROR:  column "cancelled" does not exist', ec.NO_COLUMN, "postgresql", "cancelled"),
    ('ERROR:  relation "order" does not exist', ec.NO_TABLE, "postgresql", "order"),
    (
        'ERROR:  column "orders.city" must appear in the GROUP BY clause or be used in an '
        "aggregate function",
        ec.GROUP_BY,
        "postgresql",
        "orders.city",
    ),
    ("ERROR:  operator does not exist: integer = text", ec.TYPE_MISMATCH, "postgresql", None),
    ('Syntax error: Unexpected identifier "orders" at [1:15]', ec.SYNTAX, "bigquery", "orders"),
    (
        "Syntax error: Expected end of input but got keyword WHERE at [3:1]",
        ec.SYNTAX,
        "bigquery",
        "WHERE",
    ),
    ("Unrecognized name: cancelled at [1:37]", ec.NO_COLUMN, "bigquery", "cancelled"),
    (
        "SELECT list expression references column city which is neither grouped nor aggregated "
        "at [1:8]",
        ec.GROUP_BY,
        "bigquery",
        "city",
    ),
    (
        "Aggregate function COUNT not allowed in WHERE clause at [1:30]",
        ec.AGG_IN_WHERE,
        "bigquery",
        "COUNT",
    ),
    ("ORA-00942: table or view does not exist", ec.NO_TABLE, "oracle", None),
    ('ORA-00904: "CANCELLED": invalid identifier', ec.NO_COLUMN, "oracle", "CANCELLED"),
    ("ORA-00979: not a GROUP BY expression", ec.GROUP_BY, "oracle", None),
    ("Query error: division by zero: 10 / 0", ec.DIV_ZERO, None, None),
    ("not authorized", ec.NOT_ALLOWED, "sql_mitra", None),
    ("something odd happened", ec.UNKNOWN, None, None),
]


@pytest.mark.parametrize(("error", "category", "dialect", "token"), ERRORS)
def test_catalog_recognises_real_errors(error, category, dialect, token):
    m = ec.match(error)
    assert (m.category, m.dialect, m.token) == (category, dialect, token)


@pytest.mark.parametrize(("error", "category", "dialect", "token"), ERRORS)
def test_every_reviewed_explanation_has_all_parts_and_no_rewrite(error, category, dialect, token):
    text = ec.explain(ec.match(error))
    for part in ("**అర్థం:**", "**సాధారణ కారణాలు:**", "**ఎక్కడ చూడాలి:**", "**Hint:**"):
        assert part in text
    assert text.endswith("ఇప్పుడు మీరే fix చేసి మళ్ళీ run చేయండి.")
    assert not rewrites_query(text)


def test_huge_tokens_are_clipped():
    m = ec.match("no such column: " + "x" * 500)
    assert m.token and len(m.token) <= 60


# ---- rewrite guard -----------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "rewrites"),
    [
        ("Try this:\n```sql\nSELECT name, city FROM customers\n```", True),
        ("Just write `select * from orders where status = 'x'`.", True),
        ("```sql\nSELECT ____\nFROM ____\nWHERE status = ____\n```", False),
        ("`SELECT` తర్వాత columns, `FROM` తర్వాత table.", False),
        ("Use `WHERE status = 'x'` here.", False),
        ("No code at all, SELECT name FROM customers in prose.", False),
    ],
)
def test_rewrites_query(text, rewrites):
    assert rewrites_query(text) is rewrites


def test_quoting_the_learners_own_query_is_not_a_rewrite():
    sql = "SELECT name FORM customers"
    fixed_by_learner = "select name from customers"
    text = f"మీ query `{fixed_by_learner}` బాగుంది"
    assert not rewrites_query(text, [sql, fixed_by_learner])


# ---- explainer: AI → guards → reviewed fallback ------------------------------


def test_without_ai_the_reviewed_explanation_is_used():
    e = error_explainer.explain("no such column: cancelled")
    assert e.source == "catalog" and e.category == ec.NO_COLUMN
    assert "`cancelled`" in e.message


def test_ai_explanation_is_used_and_prompt_carries_the_facts():
    fake = FakeProvider("ఈ error అర్థం: ____ కి quotes లేవు. మీరే fix చేయండి.")
    e = error_explainer.explain(
        'ERROR:  column "cancelled" does not exist',
        "SELECT * FROM orders WHERE status = cancelled",
        provider=fake,
    )
    assert e.source == "ai" and e.dialect == "postgresql"
    prompt = "\n".join(m.content for m in fake.calls[0])
    assert "PostgreSQL" in prompt and "status = cancelled" in prompt
    assert "**Hint:**" in prompt  # the reviewed explanation is the factual basis
    assert "Never write the corrected query" in prompt


def test_ai_rewrite_falls_back_to_reviewed_text():
    fake = FakeProvider("Fixed:\n```sql\nSELECT * FROM orders WHERE status = 'cancelled'\n```")
    e = error_explainer.explain("no such column: cancelled", "SELECT * FROM orders", provider=fake)
    assert e.source == "catalog"


def test_ai_failure_falls_back_to_reviewed_text():
    e = error_explainer.explain("no such column: cancelled", provider=FailingProvider())
    assert e.source == "catalog"


# ---- API -----------------------------------------------------------------------


def test_explain_error_endpoint_standalone(client):
    r = client.post("/explain-error", json={"error": "Unrecognized name: cancelled at [1:37]"})
    body = r.json()
    assert r.status_code == 200
    assert body["category"] == "unknown_column"
    assert body["dialect_name"] == "BigQuery"
    assert body["source"] == "catalog"
    assert "**Hint:**" in body["message"]


def test_explain_error_validates_input(client):
    assert client.post("/explain-error", json={"error": ""}).status_code == 422
    assert client.post("/explain-error", json={"error": "x" * 2001}).status_code == 422
    r = client.post("/explain-error", json={"error": "x", "attempt_id": "nope"})
    assert r.status_code == 404


def test_explain_error_inside_an_attempt_applies_the_leak_guard(make_client):
    c = make_client(FakeProvider("Just write `WHERE status = 'cancelled'` and done."))
    aid = start(c)["attempt_id"]
    wrong = "SELECT * FROM orders WHERE status = cancelled"
    event(c, aid, "SUBMIT_ATTEMPT", sql=wrong)
    body = c.post(
        "/explain-error",
        json={"error": "no such column: cancelled", "sql": wrong, "attempt_id": aid},
    ).json()
    assert body["source"] == "catalog"
    assert "status = 'cancelled'" not in body["message"]


# ---- progress ------------------------------------------------------------------


def _solve(client, learner, qid, *steps):
    aid = client.post("/attempts", json={"learner_id": learner, "question_id": qid}).json()[
        "attempt_id"
    ]
    for name, extra in steps:
        r = event(client, aid, name, **extra)
        assert r.status_code == 200, r.text
    return aid


def test_new_learner_has_empty_progress(client):
    p = client.get("/learners/fresh-learner/progress").json()
    assert p["overall_percent"] == 0 and p["attempted"] == 0
    assert p["accuracy_percent"] is None
    assert [t["topic"] for t in p["topics"]] == ["SELECT", "WHERE", "ORDER BY", "GROUP BY"]
    assert p["mistakes"] == [] and p["weak_topics"] == []


def test_progress_counts_outcomes_mistakes_and_topics(client):
    sub = "SUBMIT_ATTEMPT"
    _solve(
        client,
        "ravi",
        "select-customer-name-city",
        (sub, {"sql": "select name, city from customers"}),
    )
    _solve(
        client,
        "ravi",
        "where-cancelled-orders",
        (sub, {"sql": "SELECT * FROM orders WHERE status = cancelled"}),
        ("REQUEST_HINT", {}),
        (sub, {"sql": "SELECT * FROM orders WHERE status = 'cancelled'"}),
    )
    _solve(
        client,
        "ravi",
        "order-by-top-5-amount",
        (sub, {"sql": "SELECT order_id, amount FROM orders ORDER BY amount LIMIT 5"}),
        ("REQUEST_SOLUTION", {}),
    )
    _solve(
        client,
        "someone-else",
        "where-delivered-orders",
        (sub, {"sql": "select order_id, amount from orders where status='delivered'"}),
    )

    p = client.get("/learners/ravi/progress").json()
    assert (p["solved_independently"], p["solved_with_hints"], p["needed_solution"]) == (1, 1, 1)
    assert p["attempted"] == 3 and p["total_questions"] == 5
    assert p["overall_percent"] == 40  # 2 of 5 solved without the solution
    assert p["submissions"] == 4 and p["accuracy_percent"] == 50
    assert {m["tag"]: m["count"] for m in p["mistakes"]} == {
        "missing_quotes": 1,
        "order_direction": 1,
    }
    assert p["mistakes"][0]["label"]
    topics = {t["topic"]: t for t in p["topics"]}
    assert topics["SELECT"]["mastery_percent"] == 100
    assert topics["WHERE"] == {
        "topic": "WHERE",
        "total": 2,
        "attempted": 1,
        "solved": 1,
        "needed_solution": 0,
        "mastery_percent": 50,
    }
    assert p["strong_topics"] == ["SELECT"]
    assert p["weak_topics"] == ["ORDER BY"]
    assert p["question_outcomes"]["order-by-top-5-amount"] == "needed_solution"


def test_progress_keeps_the_best_outcome_across_retries(client):
    _solve(client, "anu", "select-customer-name-city", ("REQUEST_SOLUTION", {"confirmed": True}))
    _solve(
        client,
        "anu",
        "select-customer-name-city",
        ("SUBMIT_ATTEMPT", {"sql": "select name, city from customers"}),
    )
    p = client.get("/learners/anu/progress").json()
    assert p["question_outcomes"]["select-customer-name-city"] == "independent"
    assert p["attempted"] == 1

    # A later, worse retry must not erase an earlier independent solve.
    _solve(client, "anu", "select-customer-name-city", ("REQUEST_SOLUTION", {"confirmed": True}))
    p = client.get("/learners/anu/progress").json()
    assert p["question_outcomes"]["select-customer-name-city"] == "independent"
    assert p["solved_independently"] == 1 and p["needed_solution"] == 0


def test_opening_a_question_is_not_an_attempt(client):
    start(client, "where-cancelled-orders")
    p = client.get("/learners/test-learner/progress").json()
    assert p["attempted"] == 0 and p["question_outcomes"] == {}


def test_progress_rejects_bad_learner_ids(client):
    assert client.get("/learners/<script>/progress").status_code in (404, 422)
