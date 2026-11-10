# Security Rules

The `security-auditor` agent checks every change against this list.

## Secrets
- Never hard-code passwords, API keys, tokens or private keys.
- Read them from environment variables; keep `.env` in `.gitignore`.
- In CI, use GitHub **Secrets** (`${{ secrets.NAME }}`), never plain values.
- If a secret is ever committed: **rotate it immediately**. Deleting the commit isn't enough, because it stays in history and forks.

## Input
- Treat all external input as hostile: user input, HTTP requests, files, environment, third-party API responses.
- Validate type, length and format at the boundary.
- **SQL:** always use parameterized queries or an ORM. Never build SQL with string concatenation.
- **Shell:** never pass user input to a shell. If you must run commands, use argument arrays, not strings.
- **HTML:** escape output. Avoid `innerHTML` / `dangerouslySetInnerHTML` with user data.
- **Paths:** block `../` traversal when user input forms a file path.

## Auth
- Use established libraries for authentication, password hashing (bcrypt or argon2) and crypto. Never write your own.
- Check authorization on the server for every request, not only in the UI.
- Use least privilege: tokens and service accounts get only the permissions they need.

## Dependencies
- Keep Dependabot enabled and merge security updates promptly.
- Check new packages before adding them: maintenance, download count, typosquatting (`reqeusts` vs `requests`).

## Data
- Don't log passwords, tokens, or personal data.
- Use HTTPS for all network traffic.
- Error messages shown to users must not reveal stack traces or internal details.
