"""The real literature stage (docs/design/literature.md).

One execute_stage activity works through plan, search, screening, full text, analysis and
synthesis. Every step's results reach the database before the next step starts (papers,
run_papers, paper_texts), so an attempt that runs again after a gateway wait, a pause for the
lab balance or a crash reads finished steps back, and the gateway replays the calls it already
answered under the same idempotency keys.
"""
