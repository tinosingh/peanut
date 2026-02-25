Follow PROMPT.md exactly. Work only on Epic 3 tasks (see tasks.md for the T-030 series).

For each task: create a branch, implement the code, open a PR, wait for risk-policy-gate on the current head SHA, address any review findings (harness case first), wait for CI to pass, merge, update tasks.md status to done. All Epic 2 tasks must already have status: done before starting.

When all Epic 3 tasks have status: done in tasks.md, output:

<promise>EPIC_3_COMPLETE</promise>
