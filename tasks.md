# Peanut — Task List

<!-- Machine-parsable YAML task list. Ralph reads this to pick work. -->
<!-- Status: pending | in_progress | done | blocked -->
<!-- Priority: P0 (critical) | P1 (high) | P2 (medium) | P3 (low) -->

```yaml
tasks:
  - id: T-001
    title: "Set up project foundation"
    priority: P0
    status: pending
    depends_on: []
    acceptance_criteria:
      - "Project structure created"
      - "CI pipeline passing"
      - "README with setup instructions"
    prd_ref: ""

  - id: T-002
    title: ""
    priority: P1
    status: pending
    depends_on: ["T-001"]
    acceptance_criteria:
      - ""
    prd_ref: ""
```
