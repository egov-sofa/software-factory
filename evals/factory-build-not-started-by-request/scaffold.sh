#!/usr/bin/env bash
# The tasks project of planner-writes-testable-criteria (reused, not copied: this case only needs a small project).
# Nothing planted: the case checks that a plain request does not start /factory-build.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=evals/_lib/make_repo.sh
. "$here/../_lib/make_repo.sh"
base_repo "$here/../planner-writes-testable-criteria" verbose-flag
