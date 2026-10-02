"""Recognises common database errors from SQLite, MySQL, PostgreSQL and BigQuery
and explains them in Telugu-English. Deterministic, so every explanation here is
reviewed text; the AI (when configured) only rephrases these facts."""

import re
from dataclasses import dataclass

MAX_ERROR_LENGTH = 2000
_MAX_TOKEN = 60

SYNTAX = "syntax_error"
NO_COLUMN = "unknown_column"
NO_TABLE = "unknown_table"
GROUP_BY = "not_grouped"
AGG_IN_WHERE = "aggregate_in_where"
AMBIGUOUS = "ambiguous_column"
TYPE_MISMATCH = "type_mismatch"
UNCLOSED_STRING = "unclosed_string"
DIV_ZERO = "division_by_zero"
NOT_ALLOWED = "not_allowed"
TIMEOUT = "timeout"
UNKNOWN = "unknown"

DIALECT_NAMES = {
    "sqlite": "SQLite",
    "mysql": "MySQL",
    "postgresql": "PostgreSQL",
    "bigquery": "BigQuery",
    "oracle": "Oracle",
    "sql_mitra": "SQL Mitra practice",
}

# (dialect, category, pattern). Named group "tok" captures the name the error points at.
_PATTERNS: list[tuple[str | None, str, str]] = [
    # SQL Mitra sandbox
    (
        "sql_mitra",
        NOT_ALLOWED,
        r"not authorized|authorization denied|Only queries that return rows",
    ),
    ("sql_mitra", TIMEOUT, r"seconds లో పూర్తి కాలేదు|^interrupted$"),
    # SQLite
    ("sqlite", UNCLOSED_STRING, r'unrecognized token: "(?P<tok>\'[^"]*)"'),
    ("sqlite", SYNTAX, r'near "(?P<tok>[^"]*)": syntax error'),
    ("sqlite", SYNTAX, r"incomplete input"),
    ("sqlite", NO_COLUMN, r"no such column: (?P<tok>[\w.]+)"),
    ("sqlite", NO_TABLE, r"no such table: (?P<tok>[\w.]+)"),
    ("sqlite", AGG_IN_WHERE, r"misuse of aggregate(?: function)?:? ?(?P<tok>\w+)?"),
    ("sqlite", AMBIGUOUS, r"ambiguous column name: (?P<tok>[\w.]+)"),
    # MySQL
    ("mysql", SYNTAX, r"error in your SQL syntax.*?near '(?P<tok>[^']{0,60})"),
    ("mysql", NO_COLUMN, r"Unknown column '(?P<tok>[^']+)'"),
    ("mysql", NO_TABLE, r"Table '(?P<tok>[^']+)' doesn't exist"),
    ("mysql", AGG_IN_WHERE, r"Invalid use of group function"),
    ("mysql", AMBIGUOUS, r"Column '(?P<tok>[^']+)' in .* is ambiguous"),
    (
        "mysql",
        GROUP_BY,
        r"(?:isn't in GROUP BY|not in GROUP BY clause|only_full_group_by)"
        r"(?:.*?column '(?P<tok>[^']+)')?",
    ),
    # PostgreSQL
    ("postgresql", SYNTAX, r'syntax error at or near "(?P<tok>[^"]*)"'),
    ("postgresql", SYNTAX, r"syntax error at end of input"),
    ("postgresql", GROUP_BY, r'column "(?P<tok>[^"]+)" must appear in the GROUP BY clause'),
    ("postgresql", NO_COLUMN, r'column "(?P<tok>[^"]+)" does not exist'),
    ("postgresql", NO_TABLE, r'relation "(?P<tok>[^"]+)" does not exist'),
    ("postgresql", AGG_IN_WHERE, r"aggregate functions are not allowed in WHERE"),
    ("postgresql", AMBIGUOUS, r'column reference "(?P<tok>[^"]+)" is ambiguous'),
    ("postgresql", TYPE_MISMATCH, r"operator does not exist|invalid input syntax for type"),
    ("postgresql", UNCLOSED_STRING, r"unterminated quoted string"),
    # BigQuery
    ("bigquery", UNCLOSED_STRING, r"Unclosed string literal"),
    ("bigquery", AGG_IN_WHERE, r"Aggregate function (?P<tok>\w+) not allowed in WHERE"),
    (
        "bigquery",
        GROUP_BY,
        r"(?:references column (?P<tok>\w+) which is )?neither grouped nor aggregated",
    ),
    ("bigquery", NO_COLUMN, r"Unrecognized name: (?P<tok>\w+)"),
    ("bigquery", NO_TABLE, r"Not found: Table (?P<tok>[\w.:-]+)"),
    ("bigquery", AMBIGUOUS, r"Column name (?P<tok>\w+) is ambiguous"),
    ("bigquery", TYPE_MISMATCH, r"No matching signature for operator"),
    (
        "bigquery",
        SYNTAX,
        r"Syntax error: (?:Unexpected (?:keyword |identifier |string literal )?"
        r"\"?(?P<tok>[^\"\s\]]+)|Expected .*? but got (?:keyword |identifier )?(?P<tok2>[^\s\]]+))",
    ),
    # Oracle
    ("oracle", NO_TABLE, r"ORA-00942"),
    ("oracle", NO_COLUMN, r'ORA-00904: "?(?P<tok>[^":]+)"?: invalid identifier'),
    ("oracle", GROUP_BY, r"ORA-00979"),
    ("oracle", AGG_IN_WHERE, r"ORA-00934"),
    ("oracle", AMBIGUOUS, r"ORA-00918"),
    ("oracle", UNCLOSED_STRING, r"ORA-01756"),
    ("oracle", DIV_ZERO, r"ORA-01476"),
    ("oracle", SYNTAX, r"ORA-009(?:00|23|33|36)"),
    # same wording in several databases, so the dialect is left unnamed
    (None, DIV_ZERO, r"division by zero"),
]
_COMPILED = [(d, c, re.compile(p, re.IGNORECASE | re.DOTALL)) for d, c, p in _PATTERNS]


@dataclass(frozen=True)
class ErrorMatch:
    category: str
    dialect: str | None
    token: str | None


def _clean(token: str | None, category: str) -> str | None:
    if not token:
        return None
    token = token.replace("`", "").strip().strip("\"'")
    if category == SYNTAX:
        # MySQL quotes the rest of the query from the bad token; the first word is the culprit.
        token = token.split()[0] if token.split() else ""
    return token[:_MAX_TOKEN] or None


def match(error: str) -> ErrorMatch:
    for dialect, category, rx in _COMPILED:
        m = rx.search(error)
        if m:
            groups = m.groupdict()
            token = groups.get("tok") or groups.get("tok2")
            return ErrorMatch(category, dialect, _clean(token, category))
    return ErrorMatch(UNKNOWN, None, None)


def _t(token: str | None, fallback: str) -> str:
    return f"`{token}`" if token else fallback


def _sections(meaning: str, causes: list[str], where: str, hint: str) -> str:
    cause_lines = "\n".join(f"- {c}" for c in causes)
    return (
        f"**అర్థం:** {meaning}\n\n"
        f"**సాధారణ కారణాలు:**\n{cause_lines}\n\n"
        f"**ఎక్కడ చూడాలి:** {where}\n\n"
        f"**Hint:** {hint}\n\n"
        "ఇప్పుడు మీరే fix చేసి మళ్ళీ run చేయండి."
    )


def explain(m: ErrorMatch) -> str:
    tok = m.token
    if m.category == SYNTAX:
        at = f" {_t(tok, '')} దగ్గర" if tok else ""
        return _sections(
            f"Database కి మీ query structure అర్థం కాలేదు.{at} అది వేరే దాన్ని expect చేసింది.",
            [
                "Keyword spelling తప్పు (ఉదా: `FORM` అని రాయడం).",
                "Comma miss అవ్వడం, లేదా చివరి column తర్వాత extra comma.",
                "Clauses order తప్పు: SELECT → FROM → WHERE → GROUP BY → HAVING → ORDER BY → LIMIT.",
                "Bracket లేదా quote close చేయకపోవడం.",
            ],
            f"{_t(tok, 'Error చూపిన చోటు')} కి కొంచెం ముందు ఉన్న word / line. "
            "Mistake చాలాసార్లు error చూపిన చోటు ముందే ఉంటుంది.",
            "ఆ ముందు ఉన్న keyword spelling, commas, clauses order ఒకసారి check చేయండి.",
        )
    if m.category == NO_COLUMN:
        name = _t(tok, "ఆ column")
        return _sections(
            f"{name} అనే column database కి కనిపించలేదు.",
            [
                "Column పేరు spelling తప్పు, లేదా table లో ఆ column అసలు లేదు.",
                f"Text value కి quotes మర్చిపోవడం: quotes లేకపోతే database {name} ని column అనుకుంటుంది.",
                "SELECT లో పెట్టిన alias ని WHERE లో వాడటం (WHERE ముందే run అవుతుంది).",
                "వేరే table లో ఉన్న column ని ఈ table నుంచి అడగడం.",
            ],
            f"Query లో {name} ఎక్కడ వాడారో చూడండి.",
            f"{name} ఒక value అయితే single quotes లో ఉండాలి. Column అయితే table లో ఉన్న "
            "column పేర్లతో compare చేయండి.",
        )
    if m.category == NO_TABLE:
        name = _t(tok, "ఆ table")
        return _sections(
            f"{name} అనే table database లో కనిపించలేదు.",
            [
                "Table పేరు spelling, లేదా singular / plural తేడా (ఉదా: `order` vs `orders`).",
                "BigQuery లో `project.dataset.table` పూర్తి పేరు ఇవ్వకపోవడం.",
                "వేరే database / schema లో ఉన్న table.",
            ],
            "FROM / JOIN తర్వాత రాసిన table పేరు.",
            "అందుబాటులో ఉన్న tables list చూసి exact పేరుతో compare చేయండి.",
        )
    if m.category == GROUP_BY:
        name = _t(tok, "ఒక column")
        return _sections(
            f"Aggregate (COUNT, SUM, ...) ఉన్న query లో {name} group కూడా చేయలేదు, aggregate కూడా చేయలేదు.",
            [
                "SELECT లో aggregate function తో పాటు normal column ఉంది, కానీ GROUP BY లో ఆ column లేదు.",
            ],
            "SELECT list మరియు GROUP BY clause, రెండింటినీ పక్కపక్కన పెట్టి చూడండి.",
            "SELECT లో aggregate కాని ప్రతి column, GROUP BY లో కూడా ఉండాలి.",
        )
    if m.category == AGG_IN_WHERE:
        return _sections(
            "COUNT, SUM, AVG వంటి aggregate functions ని WHERE లో వాడలేము.",
            [
                "WHERE ఒక్కో row ని filter చేస్తుంది. ఆ సమయానికి groups ఇంకా తయారవ్వలేదు, "
                "కాబట్టి group total తెలియదు.",
            ],
            "WHERE clause లో ఉన్న aggregate function.",
            "Group మీద condition కావాలంటే, GROUP BY తర్వాత వచ్చే clause ఏదో ఆలోచించండి.",
        )
    if m.category == AMBIGUOUS:
        name = _t(tok, "ఆ column")
        return _sections(
            f"{name} ఒకటి కంటే ఎక్కువ tables లో ఉంది. ఏ table దో database కి తెలియట్లేదు.",
            ["JOIN చేసిన రెండు tables లోనూ అదే పేరుతో column ఉండటం."],
            f"Query లో {name} వాడిన ప్రతి చోటు.",
            "Column ముందు table పేరు లేదా alias పెట్టి స్పష్టంగా చెప్పండి (`table.column`).",
        )
    if m.category == TYPE_MISMATCH:
        return _sections(
            "రెండు వేర్వేరు data types ని compare / calculate చేస్తున్నారు.",
            [
                "Number column ని text value ('100') తో compare చేయడం, లేదా తిరిగి.",
                "Date ని సరైన format లో ఇవ్వకపోవడం.",
            ],
            "WHERE / JOIN conditions లో ఒకవైపు column, మరోవైపు value.",
            "Column type ఏదో check చేసి, value ని అదే type లో రాయండి.",
        )
    if m.category == UNCLOSED_STRING:
        return _sections(
            "ఒక text value కి quote open చేశారు కానీ close చేయలేదు.",
            ["Closing `'` మర్చిపోవడం.", "Text లోపల `'` ఉండటం (ఉదా: O'Brien)."],
            "Query లో ప్రతి single quote.",
            "ప్రతి opening `'` కి ఒక closing `'` ఉందో లెక్కపెట్టండి.",
        )
    if m.category == DIV_ZERO:
        return _sections(
            "ఏదో ఒక row లో 0 తో divide చేస్తున్నారు.",
            ["Denominator column లో 0 values ఉండటం."],
            "`/` ఉన్న calculation.",
            "Denominator 0 అయ్యే rows ని ఎలా handle చేయాలో ఆలోచించండి (ఉదా: `NULLIF`).",
        )
    if m.category == NOT_ALLOWED:
        return _sections(
            "SQL Mitra practice data read-only. Data మార్చే commands ఇక్కడ run అవ్వవు.",
            ["DROP, DELETE, UPDATE, INSERT, CREATE, ALTER వంటి commands."],
            "Query మొదటి keyword.",
            "Practice లో SELECT (లేదా WITH ... SELECT) queries మాత్రమే రాయండి.",
        )
    if m.category == TIMEOUT:
        return _sections(
            "Query చాలా సేపు run అవుతోంది, అందుకే ఆపేశాం.",
            [
                "JOIN condition లేకుండా tables కలపడం (ప్రతి row ప్రతి row తో కలుస్తుంది).",
                "Recursive CTE కి stop condition లేకపోవడం.",
            ],
            "JOIN / FROM లో tables, మరియు వాటి conditions.",
            "ప్రతి JOIN కి ON condition ఉందో check చేయండి.",
        )
    return _sections(
        "ఈ error ని SQL Mitra ఇంకా గుర్తుపట్టలేదు, కానీ దాన్ని చదివే పద్ధతి ఒక్కటే.",
        [
            "Error message లో ఉన్న table / column / keyword పేరు.",
            "Line number లేదా position ఉంటే, ఆ చోటు.",
        ],
        "Error చెప్పిన పేరు లేదా line, మరియు దానికి కొంచెం ముందు.",
        "Error message ని పదం పదం చదివి, అది ఏ పేరు గురించి మాట్లాడుతోందో గుర్తించండి.",
    )
