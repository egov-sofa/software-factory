# accounts

The accounts service of the shop: public user profiles over HTTP. Python 3.10 or newer, standard library only.

## Commands
- Test: `python -m unittest`
- Run: `python -m accounts.server` (listens on localhost:8080)
- Lint: none configured

## Conventions
- Code in `accounts/`, tests in `tests/` (unittest).
- Configuration comes from the environment; `.env` is never committed, `.env.example` lists the variables.
- Plans live in `docs/plans/`.
