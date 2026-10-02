# SQL Mitra: Telugu–English SQL Learning Assistant

> "Answer నాకు ఇవ్వలేదు, కానీ answer నేను కనుక్కునేలా నేర్పించింది."

SQL Mitra is an SQL mentor for Telugu-speaking learners. It teaches in natural Telugu-English and guides learners to the answer instead of handing it over. It is a product of Automation Lifestyle Hub.

**Status:** v0.1 in progress. Built: guided learning engine (M1), AI mentor through OpenRouter (M2), sandboxed SQL evaluation (M3), Streamlit learner UI (M4), Explain Error and progress (M5). Question bank: 20 questions across 6 topics. Remaining before v0.1: AI quality review (needs an API key) and testing with real learners. See [TASKS.md](TASKS.md).

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
```

Start the API and the UI in two terminals, both from the project root:

```bash
.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --port 8780
```

```bash
.venv/Scripts/python -m streamlit run frontend/streamlit_app.py --server.port 8781
```

Open http://localhost:8781 to learn. API docs are at http://localhost:8780/docs. To point the UI at a different API, set `SQL_MITRA_API_URL`. Run Streamlit from the project root so it picks up the navy/gold theme in `.streamlit/config.toml`.

After a change to the database models, delete `sql_mitra.db` (there are no migrations yet).

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

## License

[MIT](LICENSE). Copyright (c) 2026 Durga Rao Bandaru.
