#!/usr/bin/env python3
"""Set up workload identity federation so a repository's Claude review (and @claude mentions) can reach the Claude
API without a stored key. See docs/CLAUDE-SERVICES-AUTH.md.

It creates, through the Anthropic Admin API (beta), one federation rule per workflow on your existing GitHub issuer:
  <name>-pr-review    pull request runs of the repository           -> variable ANTHROPIC_FEDERATION_RULE_ID
  <name>-pr-mention   issue_comment runs on main (with --mention)   -> variable ANTHROPIC_MENTION_FEDERATION_RULE_ID
and gives the repository the IDs (identifiers, not secrets) as variables: it prints the `gh variable set` commands,
or with --set-variables runs them itself, so one command sets a repository up.

Without --apply it only shows what it would create and calls no Anthropic API (a preview). It never deletes anything,
and a rule that already exists with the same name on the issuer is reused, so it is safe to run again.

Usage:
  python3 scripts/claude_federation.py --repo OWNER/NAME --service-account svac_... --workspace wrkspc_... \\
      [--mention] [--mention-workflow-ref REF] [--review-workflow-ref REF] [--sub-prefix PREFIX] \\
      [--owner-id ID] [--rule-prefix NAME] \\
      [--issuer-url URL] [--create-issuer] [--token-lifetime 600] [--apply [--set-variables]]

  --service-account, --workspace
                 default to $FACTORY_CLAUDE_SERVICE_ACCOUNT and $FACTORY_CLAUDE_WORKSPACE, so a team that shares
                 them sets them once in its shell profile
  --sub-prefix   the repository's OIDC subject prefix; default: read with
                 `gh api repos/OWNER/NAME/actions/oidc/customization/sub` (sub_claim_prefix)
  --owner-id     the numeric ID of the repository's owner (organization or user), required as the
                 repository_owner_id claim so the rule keeps trusting the owner, not just its name, if the name is
                 ever released and taken; default: read with `gh api users/OWNER --jq .id`
  --mention-workflow-ref
                 also require this job_workflow_ref claim on the mention rule (hardening; copy the exact value from a
                 refused exchange in the Console if unsure)
  --review-workflow-ref
                 the same for the review rule. Recommended for projects: without it, anyone with write access can
                 open a pull request that edits the workflow and get tokens
  --apply        create the rules. Needs an org:admin OAuth token in ANTHROPIC_AUTH_TOKEN:
                   ant auth login --profile admin --scope "org:admin"
                   export ANTHROPIC_AUTH_TOKEN=$(ant auth print-credentials --profile admin --access-token)
                 and the Anthropic Python SDK (pip install anthropic). ANTHROPIC_API_KEY must be unset: the
                 federation endpoints reject API keys, and some clients prefer the key when both are set.
  --set-variables
                 with --apply, also set the repository variables with gh (needs admin access to the repository),
                 CLAUDE_REVIEW_ENABLED last, and warn about an ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN secret,
                 which would win over federation

Exit code 0 on success, 1 on an error, 2 on a usage error.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

GITHUB_ISSUER = "https://token.actions.githubusercontent.com"
AUDIENCE = "https://api.anthropic.com"
REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+$")


class SetupError(Exception):
    """A problem the user can fix; printed without a traceback."""


def parse_args(argv):
    p = argparse.ArgumentParser(add_help=True, description=__doc__.split("\n\n")[0])
    p.add_argument("--repo", required=True, help="OWNER/NAME of the GitHub repository")
    p.add_argument("--service-account", default=os.environ.get("FACTORY_CLAUDE_SERVICE_ACCOUNT", ""),
                   help="svac_... the rules mint tokens for; default: $FACTORY_CLAUDE_SERVICE_ACCOUNT")
    p.add_argument("--workspace", default=os.environ.get("FACTORY_CLAUDE_WORKSPACE", ""),
                   help="wrkspc_... the tokens act in (and are billed to); default: $FACTORY_CLAUDE_WORKSPACE")
    p.add_argument("--mention", action="store_true", help="also create the @claude mention rule")
    p.add_argument("--mention-workflow-ref", default="", help="extra job_workflow_ref claim for the mention rule")
    p.add_argument("--review-workflow-ref", default="", help="extra job_workflow_ref claim for the review rule")
    p.add_argument("--sub-prefix", default="", help="OIDC subject prefix; default: read it with gh")
    p.add_argument("--owner-id", default="", help="numeric ID of the owner; default: read it with gh")
    p.add_argument("--rule-prefix", default="", help="rule name prefix; default: the repository name")
    p.add_argument("--issuer-url", default=GITHUB_ISSUER)
    p.add_argument("--create-issuer", action="store_true", help="create the issuer if the organization has none")
    p.add_argument("--token-lifetime", type=int, default=600, help="seconds, default 600")
    p.add_argument("--apply", action="store_true", help="create the rules (default: preview only)")
    p.add_argument("--set-variables", action="store_true",
                   help="with --apply, also set the repository variables with gh (CLAUDE_REVIEW_ENABLED last)")
    args = p.parse_args(argv)
    if not REPO_RE.match(args.repo):
        p.error(f"--repo must be OWNER/NAME, got {args.repo!r}")
    if not args.service_account.startswith("svac_"):
        p.error("--service-account must be a service account ID (svac_...), or set FACTORY_CLAUDE_SERVICE_ACCOUNT")
    if not args.workspace.startswith("wrkspc_"):
        p.error("--workspace must be a workspace ID (wrkspc_...), or set FACTORY_CLAUDE_WORKSPACE")
    if args.owner_id and not args.owner_id.isdigit():
        p.error("--owner-id must be the numeric ID of the owner (gh api users/OWNER --jq .id)")
    if not 60 <= args.token_lifetime <= 3600:
        p.error("--token-lifetime must be between 60 and 3600 seconds")
    return args


def sub_prefix_from_api(repo, data):
    """The subject prefix from GitHub's OIDC customization answer. A repository with the immutable format returns
    sub_claim_prefix with owner and repository IDs; one on GitHub's default format returns use_default."""
    prefix = data.get("sub_claim_prefix")
    if prefix:
        return prefix.rstrip(":"), None
    if data.get("use_default", False) or not data:
        return f"repo:{repo}", ("GitHub reports the default subject format; check the first exchange in the Console "
                                "and pass --sub-prefix if the real subject differs")
    raise SetupError(f"unexpected answer from GitHub for {repo}'s OIDC subject: {json.dumps(data)}")


def read_sub_prefix(repo, run=subprocess.run):
    if not shutil.which("gh"):
        raise SetupError("gh is not installed; pass --sub-prefix (see `gh api repos/OWNER/NAME/actions/oidc/customization/sub`)")
    done = run(["gh", "api", f"repos/{repo}/actions/oidc/customization/sub"],
               capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise SetupError(f"gh could not read {repo}'s OIDC subject ({done.stderr.strip() or 'no output'}); "
                         "log in with `gh auth login` or pass --sub-prefix")
    return sub_prefix_from_api(repo, json.loads(done.stdout or "{}"))


def read_owner_id(owner, run=subprocess.run):
    """The owner's numeric ID; users/OWNER answers for organizations too."""
    if not shutil.which("gh"):
        raise SetupError(f"gh is not installed; pass --owner-id (the numeric ID of {owner}: gh api users/{owner} --jq .id)")
    done = run(["gh", "api", f"users/{owner}", "--jq", ".id"], capture_output=True, text=True, check=False)
    value = (done.stdout or "").strip()
    if done.returncode != 0 or not value.isdigit():
        raise SetupError(f"gh could not read the numeric ID of {owner} ({done.stderr.strip() or value or 'no output'}); "
                         "pass --owner-id")
    return value


def build_rules(args, sub_prefix, owner_id):
    """The rules to create, as Admin API payloads without issuer_id (filled in once the issuer is known)."""
    owner, name = args.repo.split("/")
    base = args.rule_prefix or name
    common = {
        "target": {"type": "service_account", "service_account_id": args.service_account},
        "workspace_id": args.workspace,
        "oauth_scope": "workspace:developer",
        "token_lifetime_seconds": args.token_lifetime,
    }
    review_claims = {"repository_owner": owner, "repository_owner_id": owner_id, "event_name": "pull_request"}
    if args.review_workflow_ref:
        review_claims["job_workflow_ref"] = args.review_workflow_ref
    rules = [{
        "variable": "ANTHROPIC_FEDERATION_RULE_ID",
        "payload": {
            "name": f"{base}-pr-review",
            "description": f"Claude review of pull requests in {args.repo} (software factory)",
            # no ref claim: pull request runs carry refs/pull/<n>/merge, not a branch
            "match": {"subject_prefix": f"{sub_prefix}:pull_request", "audience": AUDIENCE,
                      "claims": review_claims},
            **common,
        },
    }]
    if args.mention:
        claims = {"repository_owner": owner, "repository_owner_id": owner_id, "event_name": "issue_comment"}
        if args.mention_workflow_ref:
            claims["job_workflow_ref"] = args.mention_workflow_ref
        rules.append({
            "variable": "ANTHROPIC_MENTION_FEDERATION_RULE_ID",
            "payload": {
                "name": f"{base}-pr-mention",
                "description": f"Claude answers @claude comments on pull requests in {args.repo} (software factory)",
                # issue_comment runs take the workflow from the default branch
                "match": {"subject_prefix": f"{sub_prefix}:ref:refs/heads/main", "audience": AUDIENCE,
                          "claims": claims},
                **common,
            },
        })
    return rules


def variable_values(rule_ids, org_id, args):
    """(name, value) pairs for the repository, in the order they must be set: CLAUDE_REVIEW_ENABLED comes last, so a
    pull request opened meanwhile never finds the review turned on without the IDs it needs."""
    values = [(var, rid) for var, rid in rule_ids.items()]
    values += [("ANTHROPIC_ORGANIZATION_ID", org_id),
               ("ANTHROPIC_SERVICE_ACCOUNT_ID", args.service_account),
               ("ANTHROPIC_WORKSPACE_ID", args.workspace),
               ("CLAUDE_REVIEW_ENABLED", "true")]
    return values


def variable_commands(repo, rule_ids, org_id, args):
    """The gh commands that give the repository the IDs; rule_ids maps variable name to rule ID."""
    return [f"gh variable set {var} --repo {repo} --body {val}" for var, val in variable_values(rule_ids, org_id, args)]


# A repository secret with one of these names wins over federation (docs/CLAUDE-SERVICES-AUTH.md).
OVERRIDING_SECRETS = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")


def set_variables(repo, values, run=subprocess.run):
    """Set the repository variables with gh, in order. Stops at the first failure, before CLAUDE_REVIEW_ENABLED, so
    the review is never turned on half-configured. Returns the names of secrets that would override federation."""
    if not shutil.which("gh"):
        raise SetupError("gh is not installed; set the variables with the commands printed without --set-variables")
    for name, value in values:
        # list arguments, no shell: the values never pass through a command line parser
        done = run(["gh", "variable", "set", name, "--repo", repo, "--body", value],
                   capture_output=True, text=True, check=False)
        if done.returncode != 0:
            raise SetupError(f"gh could not set {name} on {repo} ({done.stderr.strip() or 'no output'}); setting a "
                             "variable needs admin access to the repository. Nothing after it was set, "
                             "CLAUDE_REVIEW_ENABLED included")
        print(f"variable: {name} set")
    done = run(["gh", "secret", "list", "--repo", repo, "--json", "name", "--jq", ".[].name"],
               capture_output=True, text=True, check=False)
    if done.returncode != 0:
        print(f"note: could not list the secrets of {repo}; check by hand that it has no "
              f"{' or '.join(OVERRIDING_SECRETS)} secret", file=sys.stderr)
        return []
    present = set((done.stdout or "").split())
    return [s for s in OVERRIDING_SECRETS if s in present]


def make_client():
    if os.environ.get("ANTHROPIC_API_KEY"):
        raise SetupError("unset ANTHROPIC_API_KEY first: the federation endpoints reject API keys and need an "
                         "org:admin OAuth token in ANTHROPIC_AUTH_TOKEN")
    if not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        raise SetupError("set ANTHROPIC_AUTH_TOKEN to an org:admin OAuth token:\n"
                         '  ant auth login --profile admin --scope "org:admin"\n'
                         "  export ANTHROPIC_AUTH_TOKEN=$(ant auth print-credentials --profile admin --access-token)")
    try:
        import anthropic
    except ImportError as ex:
        raise SetupError("install the Anthropic Python SDK first: pip install anthropic") from ex
    return anthropic.Anthropic()


def apply(client, args, rules):
    """Create the rules that do not exist yet; returns ({variable: rule_id}, organization_id)."""
    org = client.beta.organization
    issuers = [i for i in org.federation.issuers.list() if i.issuer_url == args.issuer_url and not i.archived_at]
    if issuers:
        issuer = issuers[0]
        print(f"issuer: {issuer.name} ({issuer.id})")
    elif args.create_issuer:
        issuer = org.federation.issuers.create(name="github-actions", issuer_url=args.issuer_url,
                                               jwks={"type": "discovery"})
        print(f"issuer: created {issuer.name} ({issuer.id})")
    else:
        raise SetupError(f"no federation issuer for {args.issuer_url} in this organization; create it in the "
                         "Console (Workload identity, Connect workload, GitHub Actions) or pass --create-issuer")
    existing = {r.name: r for r in org.federation.rules.list(issuer_id=issuer.id) if not r.archived_at}
    ids = {}
    for rule in rules:
        payload = rule["payload"]
        found = existing.get(payload["name"])
        if found:
            print(f"rule:   {payload['name']} exists ({found.id}), reused; check its match if the repository changed")
            ids[rule["variable"]] = found.id
            continue
        created = org.federation.rules.create(issuer_id=issuer.id, **payload)
        print(f"rule:   created {payload['name']} ({created.id})")
        ids[rule["variable"]] = created.id
    return ids, org.retrieve().id


def main(argv):
    args = parse_args(argv)
    try:
        prefix, warning = (args.sub_prefix.rstrip(":"), None) if args.sub_prefix else read_sub_prefix(args.repo)
        if warning:
            print(f"warning: {warning}", file=sys.stderr)
        owner_id = args.owner_id or read_owner_id(args.repo.split("/")[0])
        rules = build_rules(args, prefix, owner_id)
        if not args.review_workflow_ref:
            print("note: without --review-workflow-ref, any pull request from a branch of the repository can get "
                  "tokens, including one that edits the workflow; anyone with write access can do that. For a "
                  "project calling the factory at @v1, pass "
                  "OWNER/software-factory/.github/workflows/reusable-claude-review.yml@refs/tags/v1 "
                  "(docs/CLAUDE-SERVICES-AUTH.md).", file=sys.stderr)
        if not args.apply:
            print(f"Preview for {args.repo} (nothing is created; add --apply to create the rules)\n")
            for rule in rules:
                print(json.dumps({"issuer_url": args.issuer_url, **rule["payload"]}, indent=2))
            placeholders = {r["variable"]: "fdrl_..." for r in rules}
            if args.set_variables:
                print("\nWith --apply, --set-variables then sets these repository variables, in this order:")
            else:
                print("\nThen give the repository the IDs (or add --set-variables to have them set):")
            print("\n".join(variable_commands(args.repo, placeholders, "<organization-id>", args)))
            return 0
        ids, org_id = apply(make_client(), args, rules)
        if not args.set_variables:
            print("\nGive the repository the IDs (they are identifiers, not secrets):")
            print("\n".join(variable_commands(args.repo, ids, org_id, args)))
            print("\nMake sure the repository has no ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN secret: either would "
                  "win over federation.")
            return 0
        overriding = set_variables(args.repo, variable_values(ids, org_id, args))
        if overriding:
            print(f"warning: {args.repo} has the secret(s) {', '.join(overriding)}, which win over federation; "
                  f"delete them: gh secret delete NAME --repo {args.repo}", file=sys.stderr)
        print(f"\n{args.repo} is set up: its next pull request is reviewed (if it has the claude-review workflow). "
              "Each token exchange shows in the rule's authentication history in the Claude Console.")
        return 0
    except SetupError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
