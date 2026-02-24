# Peanut

## Project Overview

<!-- Brief description of the project and its purpose -->

## Conventions

### Single Source of Truth
- All configuration lives in one place. Never hardcode values that belong in config.
- Task status is tracked in `tasks.md`. Always update it after completing work.

### Code Quality
- **Test before commit**: Every change must have passing tests before committing.
- **Small commits**: One logical change per commit. Prefix with `feat:`, `fix:`, `test:`, `refactor:`, `chore:`.
- **No dead code**: Remove unused imports, variables, and functions. Don't comment out code.

### Testing
- Tests live in `tests/` mirroring `src/` structure.
- Every new function or module needs tests.
- Run the full test suite before marking a task as done.

### Code Review Checklist
Before marking any task complete, verify:
- [ ] All acceptance criteria from `tasks.md` are met
- [ ] Tests pass locally and in CI
- [ ] No hardcoded secrets or credentials
- [ ] Error handling covers failure cases
- [ ] Code is readable without excessive comments

## Architecture

<!-- Document key architectural decisions as they are made -->

## File Structure

```
src/          # Application source code
tests/        # Test files mirroring src/ structure
.github/      # CI/CD workflows
PRD.md        # Product requirements
tasks.md      # Task tracking (YAML)
ralph.yml     # Ralph Loop config
PROMPT.md     # Autonomous agent prompt
```
