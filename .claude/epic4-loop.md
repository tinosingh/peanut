Follow PROMPT.md exactly. Work only on Epic 4 tasks (see tasks.md for the T-040 series).

For each task: create a branch, implement the code, open a PR, wait for risk-policy-gate on the current head SHA, address any review findings (harness case first), wait for CI to pass, merge, update tasks.md status to done. All Epic 3 tasks must already have status: done before starting.

When all Epic 4 tasks have status: done in tasks.md, output:

<promise>EPIC_4_COMPLETE</promise>
