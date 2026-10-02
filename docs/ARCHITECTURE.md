# Architecture (v0.1)

```
Frontend (Streamlit, M4)
        │ HTTP/JSON
FastAPI backend
  ├── api/              routes + request/response schemas (input validation)
  ├── learning_engine/  state machine (pure) → mentor text → leak guard → persist
  ├── sql_engine/       evaluator (M1: normalized compare; M3: sqlglot + sandbox execution)
  ├── database/         SQLAlchemy models, SQLite (Postgres-ready)
  └── ai/               (M2) AIProvider interface + OpenRouter adapter
        │
LLM provider (M2, OpenRouter)
```

## Main decisions

- **Code owns the teaching state; the LLM only writes the language.** See [LEARNING_ENGINE.md](LEARNING_ENGINE.md).
- **Correctness is deterministic.** From M3, a query is correct when it parses and its result set matches the reference query's result set on a seeded, read-only SQLite database. The LLM explains a verdict the code has already reached; it never produces the verdict.
- **SQLite with SQLAlchemy 2.0.** Zero infrastructure now. Moving to Postgres or Supabase only needs a different `DATABASE_URL`.
- **One AI provider adapter (OpenRouter) behind an interface.** More adapters only get added when there is a real need.
- **Streamlit before React.** The goal right now is to validate the teaching loop, not to polish the UI.

## Data model (M1)

| Table | Purpose |
|---|---|
| `questions` | Prompt, topic, difficulty, concepts, authored hints, `correct_sql` (never exposed through the API) |
| `attempts` | One learner on one question: state, hint_level, failed_attempts, solved, saw_solution. UUID ids. |
| `attempt_events` | Append-only log of every transition, including submitted SQL and the mentor message shown |

`mistakes` and `progress` (Phase 3) will be derived from `attempt_events` rather than written separately.

## API (M1)

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | |
| GET | `/questions`, `/questions/{id}` | No solutions or hints |
| POST | `/attempts` | `{learner_id, question_id}` → starts at QUESTION_RECEIVED |
| GET | `/attempts/{id}` | Resume: current state + last mentor message |
| POST | `/attempts/{id}/events` | `{event, sql?, confirmed?}` → `409 {code, message}` for transitions that are not allowed |

Each turn response includes `allowed_events` and `solution_needs_confirmation`, so the UI can enable the right buttons without duplicating engine logic.

## Security

- No secrets in code. `.env` is git-ignored; `.env.example` documents the variables.
- Input validation: learner_id is limited to `[A-Za-z0-9_-]{1,64}`, SQL to 5,000 characters, and `sql` is only accepted on SUBMIT_ATTEMPT.
- Attempt ids are random UUIDs. There are no accounts in v0.1, so anyone holding an id can read that attempt. This is acceptable for a local MVP; accounts are Phase 6.
- From M3, student SQL runs only against a read-only SQLite connection with a statement allowlist (SELECT/WITH only).
