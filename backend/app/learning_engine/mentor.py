"""Canned Telugu-English mentor messages, one per state. M2 swaps this for an
LLM call fed by the same inputs; the state is always decided before this runs."""

from dataclasses import dataclass

from .machine import Progress
from .states import State

CLAUSE_MEANINGS = {
    "SELECT": "Output లో ఏ columns రావాలో చెబుతుంది.",
    "FROM": "ఏ table నుంచి data తీసుకోవాలో చెబుతుంది.",
    "WHERE": "Conditions ప్రకారం rows ని filter చేస్తుంది.",
    "AND": "ఇంకో condition కలుపుతుంది. రెండూ true అయిన rows మాత్రమే వస్తాయి.",
    "OR": "ఇంకో condition కలుపుతుంది. ఏదో ఒకటి true అయినా row వస్తుంది.",
    "GROUP BY": "ఒకే value ఉన్న rows ని ఒక group గా కలుపుతుంది.",
    "HAVING": "Groups ని filter చేస్తుంది (aggregate తర్వాత).",
    "ORDER BY": "Result ని sort చేస్తుంది.",
    "LIMIT": "ఎన్ని rows కావాలో limit చేస్తుంది.",
}


@dataclass(frozen=True)
class QuestionContent:
    id: str
    prompt_text: str
    concepts: list[str]
    structure_hint: str
    strong_hint: str
    correct_sql: str


def _explain_lines(sql: str) -> str:
    out = []
    for i, line in enumerate(sql.strip().splitlines(), start=1):
        upper = line.strip().upper()
        meaning = next(
            (m for kw, m in CLAUSE_MEANINGS.items() if upper.startswith(kw)),
            "",
        )
        out.append(f"{i}. `{line.strip()}`" + (f" → {meaning}" if meaning else ""))
    return "\n".join(out)


def compose(p: Progress, q: QuestionContent, *, facts: tuple[str, ...] = ()) -> str:
    s = p.state
    if s is State.QUESTION_RECEIVED:
        return (
            f"కొత్త question:\n\n{q.prompt_text}\n\n"
            "ముందు question ని జాగ్రత్తగా చదవండి. "
            "Explain నొక్కండి, లేదా నేరుగా query రాసి try చేయండి."
        )
    if s is State.QUESTION_EXPLAINED:
        return (
            "ఈ question లో మనం ఏం కనుక్కోవాలో first understand చేద్దాం.\n\n"
            f"Question: {q.prompt_text}\n\n"
            "ఆలోచించండి:\n"
            "1. Output లో ఏ columns రావాలి?\n"
            "2. ఏ table నుంచి data తీసుకోవాలి?\n"
            "3. ఏమైనా filter, sorting లేదా calculation అవసరమా?"
        )
    if s is State.CONCEPT_HINT:
        concepts = ", ".join(f"`{c}`" for c in q.concepts)
        return (
            f"ఈ question కి కావాల్సిన concepts: {concepts}\n\n"
            "ప్రతి concept ఇక్కడ ఎందుకు అవసరమో ఆలోచించండి. తర్వాత query రాయడానికి try చేయండి."
        )
    if s is State.STRUCTURAL_HINT:
        return (
            "Query structure ఇలా ఉంటుంది. ఖాళీలు (____) మీరే నింపాలి:\n\n"
            f"```sql\n{q.structure_hint}\n```\n\n"
            "ప్రతి ____ దగ్గర ఏం రావాలో ఆలోచించి try చేయండి."
        )
    if s is State.ERROR_ANALYSIS:
        if facts:
            checks = "Checker ఏం కనుక్కుందంటే:\n" + "\n".join(f"- {f}" for f in facts)
        else:
            checks = (
                "మీ query ని question తో మళ్ళీ compare చేయండి:\n"
                "- Columns సరిగ్గా ఉన్నాయా?\n"
                "- Filter condition సరిగ్గా ఉందా?\n"
                "- Text values కి quotes పెట్టారా?"
            )
        return (
            "ఇంకా correct కాలేదు. పర్వాలేదు, ఇది learning లో భాగమే.\n\n"
            f"{checks}\n\n"
            f"Attempt {p.failed_attempts} అయింది. మళ్ళీ try చేయండి."
        )
    if s is State.STRONG_HINT:
        return f"Strong hint:\n\n{q.strong_hint}\n\nఇప్పుడు query complete చేసి submit చేయండి."
    if s is State.SOLVED:
        how = (
            "ఒక్క hint కూడా లేకుండా!" if p.hint_level == 0 else f"{p.hint_level} hint(s) తో solve చేశారు."
        )
        return f"Correct! మీ query సరిగ్గా పని చేసింది. Answer మీరే కనుక్కున్నారు. {how}"
    if s is State.FINAL_SOLUTION:
        return (
            f"సరే, final solution ఇదిగో:\n\n```sql\n{q.correct_sql}\n```\n\n"
            "ఇప్పుడు ప్రతి line ఎందుకు ఉందో explanation చూద్దామా?"
        )
    if s is State.EXPLANATION:
        return f"ఈ query ని line-by-line చూద్దాం:\n\n{_explain_lines(q.correct_sql)}"
    if s is State.SIMILAR_PRACTICE:
        return "Understanding confirm చేసుకోవడానికి ఇలాంటి ఇంకో question try చేద్దాం."
    raise AssertionError(f"no message for {s}")


SAFE_FALLBACK = "Hint తయారు చేయడంలో చిన్న problem వచ్చింది. మళ్ళీ hint అడగండి."
