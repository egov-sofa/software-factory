# Definition of Done

A change is **done** only when every box is checked. The `reviewer` agent checks this list.

## Functionality
- [ ] Every acceptance criterion in the plan is met
- [ ] Edge cases are handled: empty input, invalid input, missing data, large data
- [ ] Errors are handled with helpful messages

## Quality
- [ ] Lint passes with no new warnings
- [ ] Build passes
- [ ] Code follows [CODING-STANDARDS.md](CODING-STANDARDS.md) and matches the surrounding style
- [ ] No leftover debug code (`console.log`, `print`, commented-out code)

## Tests
- [ ] New behavior has tests
- [ ] Bug fixes include a test that reproduces the bug
- [ ] The full test suite passes

## Security
- [ ] No secrets in code or commits
- [ ] User input is validated
- [ ] Checked against [SECURITY.md](SECURITY.md)

## Docs
- [ ] README updated if usage, setup or configuration changed
- [ ] CHANGELOG entry added for user-visible changes
- [ ] New environment variables added to `.env.example`
