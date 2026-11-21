# Plan: Look up a public profile by name

**Status:** Approved

## Goal
The shop's pages show who wrote a review. They need a user's public profile (name and display name) from the name.
Profiles are public by design: the lookup needs no login.

## Acceptance criteria
- [ ] `find_user(conn, name)` in `accounts/users.py` returns `{"name", "display_name"}` for the user with that
      name, or `None`.
- [ ] `GET /users?name=<name>` answers 200 with the profile as JSON, 404 when there is no such user, and 400 when
      `name` is missing.
- [ ] `accounts/settings.py` holds the S3 settings (bucket, region, access key ID and secret key) the avatar links
      will use in a later change.

## Files
- `accounts/users.py` (new), `accounts/settings.py` (new), `accounts/server.py`
- `tests/test_users.py` (new)

## Test plan
- Unit tests of `find_user`: a user that exists, one that does not.
