# Phase 1 exit checks

Run on 2026-10-30 against the real OpenRouter (free models). The stack was the dev compose
(Postgres, Valkey, Temporal) plus the API, gateway and worker at commit b757da9, through Caddy at
http://localhost:8080. The exit criteria are in docs/PLAN.md (Roadmap, phase 1).

| Check | Result | Evidence |
|---|---|---|
| A run makes a real LLM call, waits, is approved | Pass | Run `15f10814`: a free model (`nvidia/nemotron-3-ultra-550b-a55b:free`) wrote a six-query plan on the topic. Approved with the button in the browser; the run completed. |
| A run is cancelled mid-call | Pass | Run `7fe3fe89`: cancelled 4 s into the planner's call. The run closed as cancelled once the stage stopped, about 5 s later. The call in flight finished at $0, no further call was made, no output was stored, and the run never reopened. |
| Killing a worker resumes the run | Pass | Run `bf6befca`: the worker was killed with SIGKILL 8 s into the stage. Temporal retried the stage on a new worker after the 2-minute heartbeat timeout, and the run reached awaiting approval. The first call was replayed from the journal (`replayed: true`, no new row): nothing was paid twice. |
| Ledger = OpenRouter usage | Pass, free calls only | OpenRouter reports $0 (`usage` and `usage_daily`). The journal holds only free calls: settled at $0, released after provider 429s, none still reserved. The account has no credits, so paid calls can't be compared yet. Repeat this with a small budget after the $10 top-up. |
| A stale approval gets 409 | Pass | A wrong hash got 409 `approval.stale`. The real approval got 202, and sending it again got 409 `approval.duplicate`. |
| A viewer can't approve | Pass | Signed in as the seeded viewer `mateo.silva@lab.test`: the run is visible with `can_steer: false`, and an approval gets 403 `permission.denied`. |

Also seen during the checks:
- The first free model in the chain (`google/gemma-4-31b-it:free`) was often rate-limited by its
  provider (429). The gateway released that attempt at no cost and the next free model answered.
- The literature stage's papers are still demo data (`literature.demo_search`) until the
  Phase 2 pipeline is connected. Only the research plan comes from the LLM.

`paused_budget` can't be triggered for real without draining the account. The workflow tests
cover it (`test_an_exhausted_lab_balance_pauses_the_run_until_calls_work_again` and the tests
after it).
