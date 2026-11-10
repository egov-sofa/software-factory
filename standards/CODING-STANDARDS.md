# Coding Standards

Language-agnostic rules. Each project's `CLAUDE.md` adds language-specific details.

## Principles
1. **Clarity over cleverness.** Code is read 10× more than it's written.
2. **Small units.** Functions do one thing. Files hold one concept. If you can't name it, split it.
3. **Match the surroundings.** Follow the existing style of the file and project, even if you'd do it differently.
4. **No speculative code.** Build what the plan needs now, not what might be needed someday.
5. **Fail loudly.** Validate inputs at boundaries (user input, APIs, files). Never swallow errors silently.

## Naming
- Names describe *what*, not *how*: `activeUsers`, not `filteredList2`.
- Booleans read as questions: `isValid`, `hasAccess`.
- Functions are verbs: `calculateTotal()`, `sendInvite()`.
- Follow the language convention: `camelCase` in JS/TS, `snake_case` in Python, `PascalCase` for types and classes.

## Comments
- Explain **why**, not what. The code already says what.
- Delete commented-out code; git remembers it.
- Mark known shortcuts as `TODO(reason):`.

## Errors
- Handle errors at the level that can do something useful about them.
- Error messages say what happened **and** what to do: `"Config file not found at X. Run 'init' first."`

## Tests
- Every new behavior gets a test. Every bug fix gets a test that would have caught it.
- Test behavior, not implementation details.
- Name tests as sentences: `returns empty list when no users match`.
- Tests must be deterministic: no real network, no real time, no shared state between tests.

## Dependencies
- Prefer the standard library. Each new dependency needs a reason.
- Pin versions with a lockfile (`package-lock.json`, `uv.lock` / `requirements.txt`).
- Don't add a dependency for something under ~20 lines of code.

## Configuration
- Configuration comes from environment variables or config files, never hard-coded.
- Provide a `.env.example` listing every variable (with fake values). The real `.env` is git-ignored.
