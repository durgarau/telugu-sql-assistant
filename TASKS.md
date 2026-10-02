# Tasks

## M1: Learning-engine skeleton ✅ (2026-10-02)

- [x] State, Event and Outcome enums
- [x] Pure transition function with solution gating, an earned strong hint, and a confirm-before-reveal step
- [x] Runtime solution-leak guard
- [x] SQLite models: questions, attempts, attempt_events
- [x] Seed bank of 5 questions (SELECT, WHERE ×2, ORDER BY, GROUP BY)
- [x] FastAPI: questions, start attempt, post event, resume attempt
- [x] Canned Telugu-English mentor messages
- [x] 84 tests, including exhaustive reachability checks; mutation-checked
- [x] Live smoke run against a real server and SQLite file

**Known limits (expected; addressed by later milestones):**
- The evaluator is a normalized string compare, so correct-but-different queries fail (M3).
- The ERROR_ANALYSIS message is generic: it asks about quotes even when the actual mistake is GROUP BY (M2/M3).
- The strong hint and the line-by-line explanation are authored or generic, not tailored to the learner (M2).

## M2: Telugu-English AI mentor (code done; live review pending)

- [x] `ai/` package: `AIProvider` interface and `OpenRouterProvider` (key and model from env; httpx; timeouts; every failure raised as `AIProviderError`)
- [x] Prompt templates for 6 states; need-to-know `Material` (prompts only include what the learner has already seen)
- [x] `correct_sql` never reaches the AI in a non-reveal state; tested at the data boundary and in the prompt text
- [x] Guard upgraded to also block hidden answer lines (e.g. `GROUP BY city`), not only the full query
- [x] Canned fallback when there is no key, the provider fails, or a leak is blocked; `mentor_source` recorded per event
- [x] Tests that never call a real API, even when a key is in `.env`; 191 tests; 3 mutation checks all caught
- [x] docs/PROMPT_DESIGN.md
- [ ] **Blocked on API key:** generate hints for every question × state with a real model, review the Telugu-English quality, tune the system prompt
- [ ] Choose the production model (cost vs Telugu quality) once the review is done

## M3: Real SQL evaluation ✅ (2026-10-02)

- [x] Practice dataset `data/practice.sql`: 11 customers and 22 orders across 8 Indian cities, distinct amounts (no top-N ties), NULLs for later lessons
- [x] Sandbox: fresh in-memory DB per query, SQLite authorizer (reads only), `query_only`, 2-second time limit, 1,000-row cap
- [x] sqlglot for friendly "not allowed" messages and AST mistake detection; SQLite's own message shown for errors
- [x] Correct = same columns and same rows as the reference (row order only matters when the reference has ORDER BY), so any equivalent query passes
- [x] 9 mistake tags: missing quotes, `= NULL`, `IN (a OR b)`, aggregate in WHERE, missing GROUP BY, ORDER BY direction, missing ORDER BY, missing LIMIT, wrong LIMIT
- [x] Checker facts go to the canned and AI error feedback; tested never to reveal the answer
- [x] Learner sees their own result rows (the expected result is never sent)
- [x] Destructive SQL rejected with 422 and does not use up an attempt
- [x] `verdict` and `mistake_tags` stored per event (input for Phase 3 mistake memory)
- [x] Guard no longer blocks quotes of the learner's own SQL
- [x] 252 tests; 4 mutation checks caught (removing the time limit makes the runaway test hang rather than fail)

**Known limits:**
- SQLite rules only. Double-quoted strings (`"cancelled"`) are accepted by SQLite but are identifiers in Postgres and BigQuery; a teaching tip for this is on the backlog.
- A case-mismatched value (`'Cancelled'`) gets correct but generic feedback ("0 rows"); no dedicated tag yet.
- No schema migrations: delete `sql_mitra.db` after model changes. Add Alembic before any shared deployment.
- No pytest-timeout, so a sandbox regression on timeouts would hang CI rather than fail it.

## M4: Streamlit UI ✅ (2026-10-02)

- [x] `frontend/streamlit_app.py` + `frontend/api_client.py`; all teaching logic stays in the API
- [x] Sidebar topic and question picker, in curriculum order from the API
- [x] Question card with hint count, wrong-attempt count and stage
- [x] SQL editor, Check Query, verdict, database error and the learner's own result table
- [x] Practice-tables panel (`GET /practice/schema`: columns, types, 3 sample rows)
- [x] Mentor panel: Explain / Hint / Solution while working; Line-by-line / Similar question when finished; "next question" button
- [x] Early "Solution" shows the server's Telugu nudge with "try a hint first" or "show anyway"
- [x] Hint stays clickable while working, so the server can explain when a hint isn't available yet
- [x] "Similar question" stays at the learner's level: same topic, then same difficulty, then the nearest topic (it was jumping beginners to the Intermediate GROUP BY question)
- [x] Navy/gold ALH theme; emoji avatars (the default avatar was orange)
- [x] 12 AppTest UI tests that drive the real UI against the real backend in-process; 269 tests total
- [x] Browser walkthrough on desktop (1366×900) and mobile (375×812): full loop, no console errors

**Section 28 success criteria:** steps 1–12 all work. Step 4 ("understand in Telugu-English") currently uses the canned explanation; the AI explanation needs the OpenRouter key (M2).

**Known limits:**
- On a phone the mentor panel sits below the editor and tables, so learners scroll to reach Hint/Explain; the fixed-height chat box leaves empty space early on.
- One question per topic for SELECT/ORDER BY/GROUP BY, so "similar question" often moves to another topic. Phase 2 grows the bank.
- Progress resets when the browser session ends (no accounts; by design for v0.1).

## M5: Explain Error + basic progress (next)

- [ ] "Explain Error" panel: paste a database error, get a Telugu-English explanation and a hint, not a rewritten query
- [ ] Per-session progress view: solved independently / with hints / needed solution, from `attempt_events`
- [ ] Phone layout: mentor actions reachable without scrolling past the tables
