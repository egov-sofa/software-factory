#!/usr/bin/env bash
# The catalog project with the off-by-one of reviewer-finds-off-by-one (reused, so both cases plant the same bug),
# without the review folder: /factory-review prepares it.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=evals/_lib/make_repo.sh
. "$here/../_lib/make_repo.sh"
fixture="$here/../reviewer-finds-off-by-one"
base_repo "$fixture" paginate
commit_change "$fixture" paginate
