# Learning Engine

The learning engine is the product's core. It decides what the learner may see next.
The mentor text (canned in M1, written by an LLM from M2) only phrases a state the engine has already chosen.

Code: `backend/app/learning_engine/`

| File | Role |
|---|---|
| `states.py` | `State`, `Event` and `Outcome` enums |
| `machine.py` | Pure transition function `apply(progress, event)` and `allowed_events(progress)`. No I/O. |
| `mentor.py` | Telugu-English message for each state |
| `guard.py` | Blocks any message that contains the full solution while the learner is still working |
| `tutor.py` | Orchestration: evaluate the SQL, apply the transition, compose the message, run the guard, persist |

## States

```
QUESTION_RECEIVED ─EXPLAIN_QUESTION─▶ QUESTION_EXPLAINED
        │
        │  (all "working" states accept: EXPLAIN_QUESTION, REQUEST_HINT,
        │   SUBMIT_ATTEMPT, REQUEST_SOLUTION)
        ▼
REQUEST_HINT ladder:  CONCEPT_HINT ─▶ STRUCTURAL_HINT ─▶ STRONG_HINT
                                                   (needs ≥1 failed attempt)
SUBMIT_ATTEMPT:  wrong ─▶ ERROR_ANALYSIS (failed_attempts += 1)
                 right ─▶ SOLVED
REQUEST_SOLUTION ─▶ FINAL_SOLUTION   (needs confirmed=true if no hint and no attempt yet)

SOLVED / FINAL_SOLUTION ─REQUEST_EXPLANATION─▶ EXPLANATION
SOLVED / FINAL_SOLUTION / EXPLANATION ─REQUEST_PRACTICE─▶ SIMILAR_PRACTICE (terminal)
```

Working states: QUESTION_RECEIVED, QUESTION_EXPLAINED, CONCEPT_HINT, STRUCTURAL_HINT, ERROR_ANALYSIS, STRONG_HINT.
Reveal states, the only ones allowed to show the solution: SOLVED, FINAL_SOLUTION, EXPLANATION.

### Changes from the original spec diagram

- **STUDENT_ATTEMPT and RETRY are events, not states.** A submission is evaluated at once and lands in SOLVED or ERROR_ANALYSIS. From ERROR_ANALYSIS the learner can resubmit, so a separate RETRY state would have no behaviour of its own.
- **SOLVED was added.** The spec diagram had no state for "learner got it right", and progress tracking needs to tell an independent solve apart from a solve after seeing the answer.
- **The hint ladder is tracked separately from the state** (`hint_level` 0–3). Asking for the question explanation again does not reset the hints already used.

## How premature answers are prevented

The rule is enforced in four layers. No single layer depends on the LLM behaving.

1. **Only an explicit `REQUEST_SOLUTION` event reaches FINAL_SOLUTION.** The engine never moves there because of a free-text message or an LLM decision.
2. **Friction before zero-effort reveals.** If the learner has used no hint and made no attempt, `REQUEST_SOLUTION` returns `409 confirm_required` with a nudge to try a hint first. The client must resend with `confirmed: true`. Every reveal is recorded as `outcome = needed_solution`.
3. **The strong hint is earned.** It needs at least one failed attempt, so a learner cannot click through to a near-answer without writing any SQL.
4. **Runtime leak guard.** In any non-reveal state, a mentor message is blocked if it contains the normalized `correct_sql` or any hidden answer line (a line not already shown in the skeleton). A blocked AI reply is replaced with the canned message and a warning is logged. See [PROMPT_DESIGN.md](PROMPT_DESIGN.md).

The public API never returns `correct_sql` or the hint fields. They only leave the server through the tutor, in a reveal state.

## Tests that protect these guarantees

- `test_machine.py` explores every reachable progress state (170 at depth 7) and asserts that each reveal state was reached only by solving or by an explicit request. It also checks that `allowed_events` always agrees with `apply`.
- `test_guard_and_mentor.py` checks that no authored hint in `data/questions.json` contains its own solution, and that no mentor message in any non-reveal state does either.
- `test_api.py` covers the full learner loop over HTTP, plus the runtime guard with a deliberately leaking mentor.

Mutation checks during M1: removing the confirm gate made 2 tests fail, and putting `correct_sql` into the strong hint made 5 tests fail.

## Outcomes (input for progress tracking)

| Outcome | Meaning |
|---|---|
| `independent` | Solved with no hints |
| `with_hints` | Solved after one or more hints |
| `needed_solution` | Viewed the final solution |
