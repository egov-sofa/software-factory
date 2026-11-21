#!/usr/bin/env bash
# The catalog project on feat/paginate, with the review folder ready. Nothing planted: a correct change with tests
# for every criterion (the control of reviewer-finds-off-by-one).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=evals/_lib/make_repo.sh
. "$here/../_lib/make_repo.sh"
base_repo "$here" paginate
commit_change "$here" paginate
review_folder "$here"
