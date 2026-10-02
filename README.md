# SQL Mitra: Telugu–English SQL Learning Assistant

> "Answer నాకు ఇవ్వలేదు, కానీ answer నేను కనుక్కునేలా నేర్పించింది."

SQL Mitra is an SQL mentor for Telugu-speaking learners. It teaches in natural Telugu-English and guides learners to the answer instead of handing it over. It is a product of Automation Lifestyle Hub.

**Status:** v0.1 in progress. M1 (learning engine) and M2 (AI mentor through OpenRouter) are built. There is no UI yet.

## AI provider setup

Set `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` in `.env` (see `.env.example`). Without them the app still works, using canned Telugu-English mentor messages. Prompt design and the answer-leak protections are described in [docs/PROMPT_DESIGN.md](docs/PROMPT_DESIGN.md).

## Why it is different

An ordinary chatbot goes from question straight to answer. SQL Mitra goes question → understand → hint → attempt → feedback → retry → solution → practice. The step order is enforced in code, not left to the prompt, so the AI cannot hand out the answer early. See [docs/LEARNING_ENGINE.md](docs/LEARNING_ENGINE.md).

## Run locally

Requires Python 3.11 or later.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # Windows; use .venv/bin on macOS/Linux
cp .env.example .env
.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --port 8780
```

The API docs are at http://localhost:8780/docs.

## Test

```bash
.venv/Scripts/python -m pytest
.venv/Scripts/python -m ruff check .
```

## Docs

- [PROJECT_PLAN.md](PROJECT_PLAN.md): vision, users, MVP scope
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/LEARNING_ENGINE.md](docs/LEARNING_ENGINE.md)
- [docs/ROADMAP.md](docs/ROADMAP.md)
- [TASKS.md](TASKS.md)
