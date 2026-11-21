#!/usr/bin/env bash
# The tasks project on feat/list-limit, with no change yet: the planner plans `--limit` for the list command.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=evals/_lib/make_repo.sh
. "$here/../_lib/make_repo.sh"
base_repo "$here" list-limit
