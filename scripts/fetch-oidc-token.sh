#!/usr/bin/env bash
# Fetch a fresh GitHub OIDC token for Claude's workload identity federation into $ANTHROPIC_IDENTITY_TOKEN_FILE, for
# the Evals workflow (.github/workflows/evals.yml), which runs it once before any spend and then before each case
# (run-evals.sh --one-at-a-time, EVALS_BEFORE_EACH). A token lives 300 s and Anthropic accepts each one once (its
# jti), so every case gets its own.
#
# Needs ACTIONS_ID_TOKEN_REQUEST_URL and ACTIONS_ID_TOKEN_REQUEST_TOKEN (a job with id-token: write), curl and jq.
# Exit code 0, 1 when no token could be fetched: the file then keeps the token it had (review of #35: a failed curl
# had replaced a good token with an empty file).
set -euo pipefail
umask 077

token_file="${ANTHROPIC_IDENTITY_TOKEN_FILE:?ANTHROPIC_IDENTITY_TOKEN_FILE must name the token file}"
raw="$(curl -sSf -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
  "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=https://api.anthropic.com")" || exit 1
token="$(jq -er .value <<< "$raw")" || exit 1
printf '%s' "$token" > "$token_file.new"
mv "$token_file.new" "$token_file"
