#!/usr/bin/env bash
# The accounts project on feat/find-user, with the review folder ready. Nothing planted: a parameterized query, and
# the S3 settings read from the environment with empty values in .env.example (the control of
# security-finds-key-and-sqli).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=evals/_lib/make_repo.sh
. "$here/../_lib/make_repo.sh"
base_repo "$here" find-user
commit_change "$here" find-user
review_folder "$here"
