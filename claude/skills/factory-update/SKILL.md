---
name: factory-update
description: Update a project made or onboarded by software-factory to a newer factory release - replaces the content guard, its hooks and the shipped standards, merges the caller workflows and config files with the project's own edits, refreshes the standards block of AGENTS.md, and commits on a branch. Started by typing /factory-update [--to <release>].
argument-hint: "[--to <release>]"
disable-model-invocation: true
---

# Factory Update

Bring this project up to a newer software-factory release. Explain each step in one plain sentence as you go.
Factory location: `{{FACTORY_HOME}}`. `$FU` below is `python3 "{{FACTORY_HOME}}/scripts/factory_update.py"` (or
`python` when `python3` is missing), run from the project's root.

What happens to each file is decided by the factory's `templates/file-kinds.txt`:
- **managed** (the content guard `scripts/check_content.py`, `scripts/hooks/*`, `.factory/standards/*.md`): replaced
  whole. They carry a "Managed by software-factory" header; a local change to them is lost, and the summary says so.
- **merged** (`.github/workflows/*.yml`, `.github/dependabot.yml`, `.gitignore`, `CLAUDE.md`, ...): the factory's
  change is merged with the project's own edits (3-way); overlapping edits are left as conflict markers.
- **seeded** (everything else: `AGENTS.md`, `README.md`, the code): never changed, except the standards block between
  the `software-factory:standards` markers.

## 1. Safety checks
- `git status --porcelain` must be empty (the update refuses otherwise). If not, show the changes and ask the user to
  commit or stash them; stop.
- Fetch the factory's releases: `git -C "{{FACTORY_HOME}}" fetch --tags --quiet origin` (the update renders old and new
  factory versions from its history). If it fails (offline), say the newest release may be missing and ask whether
  to go on.

## 2. Answers file
If `.factory/answers.yml` is missing, the project was made before the factory recorded it:
- Run `$FU adopt` (add `--onboarded` when the project was onboarded with `/factory-onboard` rather than made with
  `/factory-new`; its history then has no `chore: scaffold from software-factory` commit). It prints the answers it
  inferred: the template, the names, the owner, the factory repository, the year and the base release.
- Show every answer to the user and ask them to confirm or correct each one. The base release matters most: a base
  that is too new hides factory changes silently, one that is too old only gives more conflicts, so when unsure,
  pick the older release.
- Run it again with the corrections and `--yes`: `$FU adopt [--onboarded] --set key=value ... --yes`.

## 3. Update
- Find the target: `$ARGUMENTS` if it gives `--to <release>`; else the newest stable release of the project's major
  version (`git -C "{{FACTORY_HOME}}" tag --list 'v*' --sort=-v:refname`, the major from `version:` in
  `.factory/answers.yml`). Moving to a new major version is only done when the user names it with `--to`.
- If the project is already at the target, say so and stop, unless `.factory/answers.yml` has a `_workflows_from:`
  line: the weekly update job left the workflow files behind (it cannot push them), so run the update anyway; it
  brings them in and removes that line.
- Create the branch: `git switch -c chore/factory-update-<release>`.
- Run `$FU update [--to <release>]` and show its summary. Exit code 0: clean; 1: conflicts left in files; 2: it refused
  and changed nothing (read the message: a dirty tree, broken standards markers, a release it cannot find).

## 4. Resolve, with the user
- **Conflicts** (`<<<<<<< project` ... `>>>>>>> factory <release>`): for each, show both sides and explain what each
  changes. When one side is clearly a superset, propose it; when both sides change the meaning (a different trigger,
  permission, version or command), **ask the user which to keep**; never choose alone. Remove every marker.
- **Local changes replaced** (managed files): show `git diff` of each. If the project needed that change, it belongs
  in the factory (open an issue or pull request there) or in a project file the factory does not own.
- **Needs a decision**: "deleted here, changed in the factory" (re-add it only if the user wants the service back),
  "changed here, removed from the factory" (keep or delete, ask), files that exist here and are new in the factory.
  A file the project never wants from the factory goes into `skip:` in `.factory/answers.yml`.

## 5. Verify and commit
- `grep -rn '^<<<<<<< \|^>>>>>>> ' --exclude-dir=.git .` finds no marker left.
- Run the project's checks from `AGENTS.md` (`CLAUDE.md` in projects from before AGENTS.md), and
  `python3 scripts/check_content.py --all`. If something fails, fix it with the user before committing.
- `$FU check` exits 0 (or 3, which only says a newer release exists).
- Read the release notes between the two versions (`gh release view <tag> -R <_src_path from the answers file>` for each
  release, or the factory's tags) and commit everything:
  `chore: update from software-factory <release>`, with one line per release headline in the body.
- Suggest `/factory-ship` to open the pull request.
