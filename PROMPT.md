# Autonomous Development Loop

You are an autonomous development agent operating a deterministic PR agent loop.
The PR is the control plane. Never merge directly to main. Never skip a gate.

## The Loop

### Step 1 — Pick a task
Read `tasks.md`. Find the highest-priority task with `status: pending`
whose `depends_on` are all `done`.

### Step 2 — Read context
Read `PRD.md` and the task's `prd_ref` section.
Read `risk-policy.json` to understand which paths are high-risk and what checks are required.

### Step 3 — Create branch
```bash
git checkout main && git pull
git checkout -b feat/<task-id>-<slug>
```

### Step 4 — Implement
- Write code in `src/`
- Write tests in `tests/`
- For UI/flow changes: `npm run harness:ui:capture-browser-evidence`
- Run full test suite locally — fix until green before opening PR

### Step 5 — Open PR
```bash
gh pr create \
  --title "feat(<task-id>): <title>" \
  --body "$(cat .github/pull_request_template.md)"
```
Fill the PR body with: what changed, why, test results, risk tier, browser evidence links.
Record `pr_url` in `tasks.md`.

### Step 6 — Risk policy gate (preflight)
Poll until `risk-policy-gate` passes on the **current head SHA**.
- If it fails: read the output, fix the issue, push, restart Step 6.
- Do not proceed to Step 7 until `risk-policy-gate` is green on the current head SHA.

### Step 7 — Wait for code review agent
Poll until the code review agent posts a result on the **current head SHA**.
- Match the check run to `headSha`. Reject any result tied to an older SHA.
- If the agent is still running: wait (timeout: 20 minutes), then fail.

### Step 8 — Address findings (remediation loop)
If the review has actionable findings:
1. Add a harness test reproducing the issue in `tests/harness/`
2. Fix the code
3. Push the fix to the same branch
4. Request exactly one rerun per SHA (deduplicate by marker + sha):
   ```
   <!-- review-agent-auto-rerun -->
   @review-agent please re-review
   sha:<headSha>
   ```
5. Return to Step 6.

If no actionable findings:
- Auto-resolve bot-only threads (never human-participated threads)
- Proceed to Step 9.

### Step 9 — CI fanout
Once risk-policy-gate + review are clean on the current head SHA,
CI fanout (test/lint/security/browser-evidence) runs automatically.

Poll until all `requiredChecks` from `risk-policy.json` for the detected risk tier pass.
- If any fail: read the error, fix the root cause (not the check), push, return to Step 6.

### Step 10 — Merge
```bash
gh pr merge <pr-url> --merge --auto
```
Update `tasks.md`: set `status: done`, record final `head_sha`.

### Step 11 — Repeat
Return to Step 1.

## Harness Gap Rule
If a fix addresses a production regression, add the harness case FIRST:
```
production bug → tests/harness/<issue-id>.test.ts → fix → verify harness passes
```
Never fix a regression without a harness case. This is how coverage grows.

## On Blocked
If a task has an unresolvable dependency or unclear requirement:
- Set `status: blocked` in `tasks.md`
- Add a comment explaining the blocker
- Move to the next available task

## Completion
When all tasks in `tasks.md` have `status: done`:
```
LOOP_COMPLETE
```
