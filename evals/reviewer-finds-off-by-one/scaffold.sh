#!/usr/bin/env bash
# The catalog project on feat/paginate, with the review folder ready. Planted: paginate() drops the last item of
# every page (items[start:last] with last an inclusive index); the tests only look at the first item of a page.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=evals/_lib/make_repo.sh
. "$here/../_lib/make_repo.sh"
base_repo "$here" paginate
commit_change "$here" paginate
review_folder "$here"
