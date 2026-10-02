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

## M3: Real SQL evaluation (next)

- [ ] Seeded read-only SQLite practice DB (customers, orders with Indian cities)
- [ ] sqlglot parse; allow only SELECT/WITH
- [ ] Run the learner query and the reference query; compare result sets (order-sensitive only when ORDER BY matters)
- [ ] Rule-based mistake tags (missing quotes, `= NULL`, `IN (a OR b)`, WHERE vs HAVING) passed to ERROR_ANALYSIS as facts
