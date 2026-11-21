#!/usr/bin/env bash
# Probe workspace: a tiny git repository on a feature branch, and a review folder inside .git with a known line.
set -euo pipefail
git init -q -b main
git config user.name "Eval Scaffold"
git config user.email "evals@example.invalid"
mkdir -p src tests
printf 'RESULT = 1\n' > src/x.py
printf 'import unittest\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.assertTrue(True)\n' \
  > tests/test_x.py
git add -A
git commit -q -m "chore: probe base"
git switch -q -c feat/probe
review="$(git rev-parse --absolute-git-dir)/factory-review"
mkdir -p "$review"
printf 'PROBE-7731-OK\n' > "$review/probe.txt"
