"""Rule-based detection of common beginner mistakes.

Tags feed the mentor's error analysis now and the learner's mistake memory
(Phase 3) later. Facts must never state the missing answer itself, only
where to look."""

import re

from sqlglot import exp

from .sandbox import schema_columns

NULL_COMPARISON = "null_comparison"
MISSING_QUOTES = "missing_quotes"
IN_WITH_OR = "in_with_or"
AGGREGATE_IN_WHERE = "aggregate_in_where"
MISSING_GROUP_BY = "missing_group_by"
ORDER_DIRECTION = "order_direction"
MISSING_ORDER_BY = "missing_order_by"
MISSING_LIMIT = "missing_limit"
LIMIT_VALUE = "limit_value"

FACTS = {
    NULL_COMPARISON: "`= NULL` / `!= NULL` ఎప్పుడూ true అవ్వదు. "
    "NULL check కోసం `IS NULL` / `IS NOT NULL` వాడాలి.",
    MISSING_QUOTES: "`{word}` అనే column ఏ table లోనూ లేదు. "
    "ఇది text value అయితే single quotes లో రాయాలి: `'...'`.",
    IN_WITH_OR: "`IN ( ... OR ... )` సరైన syntax కాదు. "
    "IN లో values ని comma తో వేరు చేయాలి: `IN ('a', 'b')`.",
    AGGREGATE_IN_WHERE: "Aggregate functions (COUNT, SUM, ...) ని WHERE లో వాడలేము. "
    "Groups ని filter చేయాలంటే HAVING వాడాలి.",
    MISSING_GROUP_BY: "SELECT లో aggregate function తో పాటు normal column కూడా ఉంది, "
    "కానీ GROUP BY లేదు. SQLite error ఇవ్వదు, కానీ result తప్పుగా వస్తుంది.",
    ORDER_DIRECTION: "ORDER BY direction (ASC / DESC) ఒకసారి check చేయండి.",
    MISSING_ORDER_BY: "Question ఒక order లో result అడుగుతోంది. Sorting ఏ column మీద, ఏ direction లో?",
    MISSING_LIMIT: "Question కొన్ని rows మాత్రమే అడుగుతోంది. Result ని limit చేయాలి.",
    LIMIT_VALUE: "LIMIT value ని question తో మళ్ళీ compare చేయండి.",
}

LABELS = {
    NULL_COMPARISON: "NULL ని `=` తో compare చేయడం",
    MISSING_QUOTES: "Text values కి quotes మర్చిపోవడం",
    IN_WITH_OR: "`IN` లోపల `OR` వాడటం",
    AGGREGATE_IN_WHERE: "Aggregate ని WHERE లో వాడటం (HAVING కావాలి)",
    MISSING_GROUP_BY: "GROUP BY మర్చిపోవడం",
    ORDER_DIRECTION: "ORDER BY direction (ASC/DESC) తప్పు",
    MISSING_ORDER_BY: "ORDER BY మర్చిపోవడం",
    MISSING_LIMIT: "LIMIT మర్చిపోవడం",
    LIMIT_VALUE: "LIMIT value తప్పు",
}

_NO_SUCH_COLUMN = re.compile(r"no such column: (\w+)", re.IGNORECASE)


def _is_null(node: exp.Expression) -> bool:
    return isinstance(node, exp.Null)


def from_tree(tree: exp.Expression) -> list[str]:
    tags = []
    for cmp in tree.find_all(exp.EQ, exp.NEQ):
        if _is_null(cmp.left) or _is_null(cmp.right):
            tags.append(NULL_COMPARISON)
            break
    for in_ in tree.find_all(exp.In):
        if any(isinstance(e, exp.Or) for e in in_.expressions):
            tags.append(IN_WITH_OR)
            break
    for select in tree.find_all(exp.Select):
        where = select.args.get("where")
        if where is not None and where.find(exp.AggFunc):
            tags.append(AGGREGATE_IN_WHERE)
        if select.args.get("group") is None and _mixes_aggregate_and_plain(select):
            tags.append(MISSING_GROUP_BY)
    return list(dict.fromkeys(tags))


def _mixes_aggregate_and_plain(select: exp.Select) -> bool:
    has_agg = has_plain = False
    for projection in select.expressions:
        if projection.find(exp.AggFunc):
            has_agg = True
        elif projection.find(exp.Column):
            has_plain = True
    return has_agg and has_plain


def from_runtime_error(message: str) -> list[str]:
    m = _NO_SUCH_COLUMN.search(message)
    if m and m.group(1).lower() not in schema_columns():
        return [MISSING_QUOTES]
    return []


def _order_keys(tree: exp.Expression) -> dict[str, bool]:
    order = tree.args.get("order")
    if order is None:
        return {}
    return {o.this.sql().lower(): bool(o.args.get("desc")) for o in order.expressions}


def against_reference(tree: exp.Expression, ref: exp.Expression) -> list[str]:
    tags = []
    ref_order, got_order = _order_keys(ref), _order_keys(tree)
    if ref_order and not got_order:
        tags.append(MISSING_ORDER_BY)
    elif any(k in got_order and got_order[k] != desc for k, desc in ref_order.items()):
        tags.append(ORDER_DIRECTION)

    ref_limit, got_limit = ref.args.get("limit"), tree.args.get("limit")
    if ref_limit is not None:
        if got_limit is None:
            tags.append(MISSING_LIMIT)
        elif got_limit.sql().lower() != ref_limit.sql().lower():
            tags.append(LIMIT_VALUE)
    return tags


def facts_for(tags: list[str], error: str | None = None) -> list[str]:
    out = []
    for tag in dict.fromkeys(tags):
        if tag == MISSING_QUOTES:
            m = _NO_SUCH_COLUMN.search(error or "")
            out.append(FACTS[tag].format(word=m.group(1) if m else "..."))
        else:
            out.append(FACTS[tag])
    return out
