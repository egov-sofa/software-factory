# Git Workflow

## Branches
- `main` is always working and deployable. Never commit to it directly.
- One branch per feature or fix, named `<type>/<short-description>`:
  - `feat/user-login`
  - `fix/crash-on-empty-cart`
  - `chore/update-deps`
  - `docs/api-examples`

## Commits: Conventional Commits
Format: `<type>(<optional scope>): <summary in imperative mood>`

| Type | Use for |
|---|---|
| `feat` | A new feature |
| `fix` | A bug fix |
| `docs` | Documentation only |
| `test` | Adding or fixing tests |
| `refactor` | A code change that neither fixes a bug nor adds a feature |
| `chore` | Tooling, dependencies, config |
| `ci` | CI/CD changes |

Examples:
```
feat(auth): add password reset via email
fix: prevent crash when cart is empty
```

Keep commits focused. "Fix typo" and "add feature" are two commits.

## Pull Requests
1. Push the branch, then open a PR to `main`.
2. Fill in the PR template (what, why, how tested).
3. CI must be green ✅.
4. Prefer **squash merge**: one clean commit per feature on `main`.
5. Delete the branch after merging.

## Never commit
- Secrets (`.env`, keys, tokens, passwords)
- Build output (`dist/`, `build/`, `__pycache__/`)
- Dependencies (`node_modules/`, `.venv/`)
- Personal editor files (`.idea/`, `.DS_Store`)
