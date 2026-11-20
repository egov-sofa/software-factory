#!/usr/bin/env bash
# Runs the spike's read-only plans on the Anthropic side, for both providers. It needs your org:admin login and never
# applies anything (docs/plans/2026-11-19-terraform-platform.md, spike).
#
#   ant auth login --profile admin --scope "org:admin"     (once)
#   bash docs/plans/2026-11-19-terraform-platform-spike/run-anthropic.sh
#
# Each anthropic/<provider>/terraform.tfvars must exist (copy terraform.tfvars.example). On a machine whose TLS is
# intercepted, Terraform cannot talk to its own plugins: prefix the command with TF_DISABLE_PLUGIN_TLS=1 (README).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# without ANTHROPIC_API_KEY: when it is set, ant prints that key instead of the profile's org:admin token
token="$(env -u ANTHROPIC_API_KEY ant auth print-credentials --profile admin --access-token)"
[[ "$token" == sk-ant-oat01-* ]] || { echo "error: ant did not return an org:admin OAuth token; log in again" >&2; exit 1; }

plan() {
  # the token reaches only this terraform process: ippontech reads ANTHROPIC_AUTH_TOKEN, mozilla ANTHROPIC_OAUTH_TOKEN
  env -u ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN="$token" ANTHROPIC_OAUTH_TOKEN="$token" \
    terraform plan -input=false -no-color "$@" 2>&1
}

for provider in ippontech mozilla; do
  dir="$here/anthropic/$provider"
  echo "== $provider"
  if [[ ! -f "$dir/terraform.tfvars" ]]; then
    echo "skipped: copy $dir/terraform.tfvars.example to terraform.tfvars and fill it in"
    continue
  fi
  cd "$dir"
  terraform init -input=false -no-color > /dev/null
  rm -f generated.tf
  echo "-- import and generate the configuration:"
  plan -generate-config-out=generated.tf | grep -E -A4 '^(Plan:|Error)' || true
  if [[ -f generated.tf ]]; then
    echo "-- plan again with the generated configuration (anything but 0 to change is a finding):"
    plan | grep -E '^(Plan:|Error)|will be (updated|replaced|created|destroyed)|^ +[~+-] ' | head -40 || true
  fi
done
