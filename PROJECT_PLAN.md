# Project Plan: SQL Mitra (Telugu–English SQL Learning Assistant)

## Problem

Telugu-speaking students learning SQL (data analytics students, college students, career switchers, interview preparers) mostly learn from English-only material. When they get stuck, AI chatbots simply give them the answer, so they copy it instead of learning.

## Product

A patient SQL mentor that explains in natural Telugu-English and refuses to hand out answers early. It walks the learner through understanding the question, the concepts involved, graded hints, feedback on their attempts, and only then the solution, followed by a similar practice question.

**Differentiator:** the enforced teaching loop combined with a natural bilingual voice. The LLM is not the differentiator.

## v0.1 scope

MUST
- Guided-learning state machine, enforced server-side
- Telugu-English mentor (one provider: OpenRouter)
- Evaluation of student SQL by executing it in a read-only sandbox and comparing results
- 20 hand-written questions across SELECT, WHERE, ORDER BY, Aggregates, GROUP BY and HAVING (easy → hard)
- Streamlit UI: question, SQL editor, mentor panel, Hint / Check / Show Solution buttons

Not in v0.1: accounts, gamification, interview mode, daily challenge, multiple dialects, a React frontend.

## Success criteria

A learner can open the app, pick a topic, get a question explained, ask for hints, submit SQL, get feedback without seeing the answer, retry, eventually view the solution with a line-by-line explanation, and try a similar question.

## Stack

FastAPI · SQLAlchemy 2 + SQLite · sqlglot (M3) · Streamlit (M4) · OpenRouter (M2) · pytest + ruff.
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the reasoning behind each choice.

## Future monetization (not now)

Free: basic lessons and practice. Pro: unlimited mentor, analytics, interview mode. Institution: dashboards for colleges and coaching centres.
