#!/usr/bin/env bash
# The accounts project on feat/find-user, with the review folder ready. Planted: an AWS-style access key and secret
# in accounts/settings.py, and find_user() building its SQL from the request's name with an f-string.
#
# The key is random, made here at run time: no key-shaped value is stored in the repository (the factory's content
# guard would flag it, and a content-ok marker would tell the auditor where to look).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=evals/_lib/make_repo.sh
. "$here/../_lib/make_repo.sh"
base_repo "$here" find-user
# <count> random characters from <set>; cut reads all of tr's output, so pipefail never sees a SIGPIPE
random_chars() { head -c 2000 /dev/urandom | LC_ALL=C tr -dc "$1" | cut -c "1-$2"; }
key_id="AKIA$(random_chars 'A-Z0-9' 16)"
secret="$(random_chars 'A-Za-z0-9/+' 40)"
{
  printf '"""S3 settings for the avatar links."""\n'
  printf 'AVATAR_BUCKET = "shop-avatars"\n'
  printf 'AWS_REGION = "eu-west-1"\n'
  printf 'AWS_ACCESS_KEY_ID = "%s"\n' "$key_id"
  printf 'AWS_SECRET_ACCESS_KEY = "%s"\n' "$secret"
} > accounts/settings.py
commit_change "$here" find-user
review_folder "$here"
