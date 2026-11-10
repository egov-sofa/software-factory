#!/usr/bin/env bash
# The single quality gate for this project. CI runs this script, and so should you before pushing.
# Fill in the commands for your language. Examples:
#   Go:     go vet ./... && go test ./...
#   Rust:   cargo clippy -- -D warnings && cargo test
#   .NET:   dotnet build --warnaserror && dotnet test
#   Java:   ./gradlew check
set -euo pipefail

echo "==> Lint"
echo "(no linter configured yet: edit scripts/check.sh)"

echo "==> Build"
echo "(no build configured yet: edit scripts/check.sh)"

echo "==> Test"
echo "(no tests configured yet: edit scripts/check.sh)"

echo "✅ All checks passed"
