# Prompt Design

Code: `backend/app/prompts/mentor_prompts.py` (templates), `backend/app/learning_engine/ai_mentor.py` (what each template may see), `backend/app/learning_engine/tutor.py` (AI → guard → canned fallback).

## Principle: the AI phrases, the engine decides

The state machine has already chosen the teaching move (concept hint, error feedback and so on) before the AI is called. The AI is never asked "should I give the answer?". It is only asked how to say the move that was chosen, in Telugu-English.

## Which states use the AI

| State | AI? | Why |
|---|---|---|
| QUESTION_RECEIVED | No | Shows the question as written; nothing to add |
| QUESTION_EXPLAINED | Yes | Explaining the question in the learner's language is the core value |
| CONCEPT_HINT | Yes | Explains why each concept is needed for this question |
| STRUCTURAL_HINT | Yes, for the guiding questions only | The teacher-written skeleton is added by code and shown word for word |
| ERROR_ANALYSIS | Yes | Feedback on the learner's actual query, which canned text cannot give |
| STRONG_HINT | Yes | Builds on the teacher-written strong hint and the learner's last query |
| SOLVED, FINAL_SOLUTION | No | Fixed text is clearer and cheaper here |
| EXPLANATION | Yes | Line-by-line explanation of the final query |
| SIMILAR_PRACTICE | No | The similar-question generator is Phase 3 |

## Need-to-know material

`ai_mentor.material_for` builds the only data a template can read. It contains what the learner has already been shown, or is being shown in this turn:

| Material | Included when |
|---|---|
| Question text, learner's SQL, failed-attempt count, last 3 mentor messages | Always |
| Concepts | hint_level ≥ 1 |
| Query skeleton | hint_level ≥ 2 |
| Teacher-written strong hint | hint_level ≥ 3 |
| `correct_sql` | Only in reveal states (SOLVED, FINAL_SOLUTION, EXPLANATION) |

Leaving `correct_sql` out of the prompt is not enough on its own, because the model can work the answer out from the question. That is why the guard below also exists.

## Leak guard

Before a message reaches the learner in a working state, `guard.leaks_solution` blocks it if it contains:
- the full normalized `correct_sql`, or
- any **hidden answer line**: a line of `correct_sql` that does not appear in the skeleton (for example `GROUP BY city` or `LIMIT 5`). `FROM <table>` lines are exempt because the question already names the table.

Matching ignores case and whitespace. If an AI reply is blocked, or the provider fails, the learner gets the tested canned message for that state. Each event records `mentor_source` as `ai`, `canned` or `fallback`, so leak and outage rates can be measured.

## System prompt rules

- Natural spoken Telugu (in Telugu script) mixed with English; SQL terms stay in English; no bookish Telugu
- Teach, don't answer: never the full query, never a finished clause the learner still has to produce; use `____` blanks or guiding questions
- Use only the supplied material
- End with one next step; about 120 words; Markdown; no greetings or emojis

## Not done yet

- **Quality review with a real model.** Needs `OPENROUTER_API_KEY` and `OPENROUTER_MODEL`. Plan: generate hints for every question × state, read them for natural Telugu-English, and tune the system prompt.
- **Exact diagnostics for ERROR_ANALYSIS** (M3): row-count differences, rule-based mistake tags such as missing quotes or `= NULL`, to be passed to the model as facts.
- **Telugu-script normalization:** the guard only looks at the SQL text; transliterated SQL in Telugu script is not a realistic leak path.
