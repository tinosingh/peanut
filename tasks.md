# Peanut — Task List

<!-- Machine-parsable YAML task list. The agent reads this to pick work. -->
<!-- Status: pending | in_progress | done | blocked -->
<!-- Priority: P0 (critical) | P1 (high) | P2 (medium) | P3 (low) -->

```yaml
tasks:
  - id: T-001
    title: "Set up project foundation"
    priority: P0
    status: pending
    depends_on: []
    branch: ""
    pr_url: ""
    head_sha: ""
    acceptance_criteria:
      - "Project structure created"
      - "risk-policy.json tuned for the stack"
      - "CI pipeline passing (risk-policy-gate + CI Pipeline)"
      - "README with setup instructions"
    prd_ref: ""

  - id: T-002
    title: ""
    priority: P1
    status: pending
    depends_on: ["T-001"]
    branch: ""
    pr_url: ""
    head_sha: ""
    acceptance_criteria:
      - ""
    prd_ref: ""
```
