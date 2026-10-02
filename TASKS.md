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

## M2: Telugu-English AI mentor (next)

- [ ] `ai/` package: `AIProvider` interface and `OpenRouterProvider` (key read from env)
- [ ] One prompt template per state in `prompts/`; the template for a state receives only the data that state may reveal
- [ ] `correct_sql` is never passed to the LLM in a non-reveal state (the guard stays as a backstop)
- [ ] Fall back to the canned mentor when the provider is down or no key is set
- [ ] Tests with a fake provider; manual review of 10 generated hints for natural Telugu-English
- [ ] docs/PROMPT_DESIGN.md
