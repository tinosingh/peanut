## Summary

<!-- What does this PR do and why? Reference the task: T-XXX -->

## Risk Tier

<!-- high | low — determined automatically by risk-policy-gate from risk-policy.json -->

## Evidence

### Tests
- [ ] All tests pass locally
- [ ] New code has test coverage in `tests/`

### Harness
- [ ] No production regression → no new harness case needed
- [ ] Production regression addressed → harness case added in `tests/harness/<issue-id>.test.*`

### Browser Evidence *(required for UI/flow changes only)*
- [ ] Not applicable — no UI or user-flow changes
- [ ] `npm run harness:ui:capture-browser-evidence` passed
- [ ] Evidence artifacts: <!-- paste links or attach screenshots -->

## Checklist
- [ ] Acceptance criteria in `tasks.md` are met
- [ ] No hardcoded secrets or credentials
- [ ] `risk-policy.json` updated if new high-risk paths introduced
- [ ] Docs updated if API or schema changed (enforced by docs drift rule)
