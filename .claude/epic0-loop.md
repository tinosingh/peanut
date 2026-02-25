Follow PROMPT.md exactly. Work only on Epic 0 tasks: T-000, T-001, T-002, T-003, T-004, T-005.

For each task: create a branch, implement the code, open a PR, wait for risk-policy-gate on the current head SHA, address any review findings (harness case first), wait for CI to pass, merge, update tasks.md status to done.

When all 6 Epic 0 tasks have status: done in tasks.md, output:

<promise>EPIC_0_COMPLETE</promise>
