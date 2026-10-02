# Roadmap

## Phase 1: Core MVP (v0.1)

| Milestone | Objective | Status |
|---|---|---|
| M1 | Learning-engine skeleton: state machine, persistence, API, canned mentor | **Done** |
| M2 | Telugu-English mentor through OpenRouter, with prompt templates per state | Code done; live quality review needs an API key |
| M3 | Real SQL evaluation: sqlglot parse, read-only sandbox execution, result-set comparison, rule-based mistake detection | Next |
| M4 | Streamlit UI covering the full 12-step loop | |
| M5 | "Explain Error" feature and a basic progress view | |

**v0.1 is done when** a learner can complete Section 28's 12-step loop on 3 questions and the engine never reveals an answer early.

## Later phases

- **Phase 2, Practice:** larger question bank (Easy/Medium/Hard per topic), seeded Indian datasets (customers, orders, payments with Hyderabad, Vijayawada and other cities), topic selection
- **Phase 3, Learning intelligence:** progress tracker, mistake memory, adaptive question choice, similar-question generator
- **Phase 4, Public demo:** Hugging Face Space, GitHub repository, screenshots
- **Phase 5, Advanced SQL:** joins, subqueries, CTEs, window functions, interview mode, daily challenge
- **Phase 6, Platform:** accounts, Postgres or Supabase, subscriptions, PWA

## Feature classification

- **MUST (v0.1):** guided state machine, Telugu-English mentor, attempt evaluation, read-only sandbox, small hand-written question bank, simple UI
- **SHOULD:** similar-question generator, mistake memory, progress dashboard, dialect notes
- **LATER:** interview mode, daily challenge, gamification, accounts, extra AI providers, other subjects (Excel, Python, Power BI)
