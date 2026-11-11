# Roadmap

A living document: the improvements planned for the factory, ranked by value, and the order of work. Most of them are
inspired by `egov-ai/claude-skills`, which already solved these problems for one repository. The strategy behind them
is in [SHARED-SERVICES.md](SHARED-SERVICES.md).

Every item has a stable ID and a status. Update the status in the same pull request that changes it, and add a dated
entry to the review log at the bottom after each new review.

**Status:** `open`, `in progress`, `done` (with the commit or pull request), `dropped` (with the reason).
**Effort:** XS under an hour, S half a day, M a day or two, L more.

## Starting point (reviewed 2026-11-11)

**What is good:** a clear agent pipeline (planner, implementer, tester, reviewer, security auditor, docs writer) with
read-only reviewers and an approval gate, layered templates, reusable CI and a self-test that scaffolds every
template.

**Where it is weak:** nothing checks the factory itself. No test shows the agents and skills behave as intended,
projects follow `@main` so one bad push breaks every project, actions are not pinned, and the "never commit secrets"
rule is written down but not enforced.

---

## Recommended improvements, highest value first

| ID | Improvement | Why | Source in claude-skills | Effort | Status |
|---|---|---|---|---|---|
| I1 | **Evals for agents and skills.** `claude plugin eval` cases per agent: reviewer finds a planted off-by-one, security auditor finds a planted key and SQL injection, planner writes testable acceptance criteria, `/factory-build` triggers from a natural request. Each case runs with and without the agent, so the report shows what it adds. Run by hand from a `workflow_dispatch` job with a cost ceiling. | A change to an agent's instructions can make it worse and nothing would notice. | `skills/*/evals/`, `scripts/ci_evals.sh`, `.github/workflows/evals.yml` | M | open |
| I2 | **Claude PR review as a shared service.** A reusable workflow that reviews each pull request against the project's own `.claude/skills/pr-review/SKILL.md`, skips drafts, has a `skip-review` label and cancels a running review on a new push. Plus an `@claude` mention workflow. Authenticates with workload identity federation, so no API key is stored. | The reviewer and security auditor already exist as checklists; CI can apply them on every pull request. | `.github/workflows/claude-code-review.yml`, `claude-mention.yml`, `docs/claude-code-review-auth.md` | M | done (#2) |
| I3 | **Versions and releases.** Tag releases `vX.Y.Z`, keep a moving major tag `v1`, have templates call `@v1` instead of `@main`, and generate release notes from Conventional Commit subjects. | `@main` means one bad push breaks every project's CI at once. | `.github/workflows/release.yml`, `scripts/release_notes.py` | S | done (#2) |
| I4 | **Supply-chain hygiene.** Pin every action to a commit SHA with its version in a comment, and add Dependabot for the factory's own workflows. | Floating `@v4` tags can change under you; only the templates had Dependabot. | every workflow, `.github/dependabot.yml` | XS | done (#2) |
| I5 | **Enforce "never commit secrets".** A content guard that blocks secrets, public IP addresses, internal host names and a private denylist, in CI on every pull request and in local pre-commit and commit-msg hooks shipped with every project. | `standards/SECURITY.md` says it, nothing enforces it. | `scripts/check_content.py`, `scripts/hooks/`, `.github/workflows/content.yml` | S | done (#2) |
| I6 | **Validate and test the factory's own scripts.** Check agent and skill frontmatter (`name` matches the file, `model` is valid, `tools` names real tools). Test `install.sh` twice into a temporary `CLAUDE_CONFIG_DIR` (own content kept, factory block replaced, backups written). Test the options of `new-project.sh` and the content guard's rules. | The self-test only scaffolds projects; a broken installer or a typo in an agent's frontmatter goes unnoticed. | `scripts/validate.py`, `scripts/tests/` | M | done (#5) |
| I7 | **Distribute as a plugin marketplace.** `.claude-plugin/marketplace.json` so agents and skills install with `/plugin install` and update with `/plugin update`. Check first whether a plugin can contribute the global `CLAUDE.md` rules; if not, keep a slim `install.sh` for that block only. | Re-running `install.sh` by hand is easy to forget. | `.claude-plugin/marketplace.json`, `scripts/build.py` | M | open |
| I8 | **Link mode for install.** `install.sh --link` symlinks agents and skills (a junction on Windows) instead of copying, so a `git pull` updates the installed copy. | Removes the "never edit `~/.claude`" trap in CUSTOMIZING.md. | `scripts/install_local.py` | S | open |
| I9 | **Review checklist for the factory repo itself.** `.claude/skills/pr-review/SKILL.md` with the factory's own rules (placeholders, template layering, shared-service compatibility, pinned actions), also usable locally as `/pr-review <n>`. | The factory's pull requests should get the same review its projects get. | `.claude/skills/pr-review/SKILL.md` | S | done (#2) |
| I10 | **Generated catalog.** Build the README's tables of agents, commands and templates from file metadata, and have CI fail when they are out of date. | Hand-kept tables drift. | `scripts/build.py --check` | S | open |
| I11 | **This roadmap.** One document with an ID and status per finding. | Keeps the plan visible and reviewable. | `docs/roadmap.md` | XS | done (#2) |
| I12 | **Reuse skills from claude-skills.** `docs-writer` uses `plain-human-english`; `planner` can draw diagrams with `architecture-diagram`. | Better docs and plans for free. | `skills/writing/plain-human-english`, `skills/architecture/architecture-diagram` | S | open |
| I13 | **Tidy the I6 review follow-ups.** Nine LOW/MINOR findings: CRLF `CLAUDE.md` message, allowlist for read-only agent tools, more `GIT_*` variables unset in test support, `sed` value escaping, shared marker check, `trap - EXIT` in `new-project.sh`, backslash-continued lines in `test_no_in_place_sed`, `[]` for empty `name`/`model`, assert the reason in `test_rejected_arguments`. | Small gaps found in review that did not block I6. | [plan](plans/2026-11-11-validate-and-test-factory-scripts.md) (Follow-ups) | XS | open |
| I14 | **Diagrams from sketches.** Every diagram in the docs is a YAML sketch in `docs/diagrams/`, drawn by the architecture-diagram skill of claude-skills (0.10.0) into `.drawio` and `.png`; `build.sh` regenerates them and `--check` compares them with their sketches. Replaces the Mermaid and ASCII diagrams and adds diagrams for the problems and the target (13 files, 15 pages). | One house style, reviewable sources, diagrams that can be regenerated instead of redrawn. | `docs/how-it-works.yaml`, `skills/architecture/architecture-diagram` | S | done (this branch) |
| I15 | **Diagram follow-ups.** (a) Report or fix in claude-skills: the trust-boundary legend sample is drawn as an empty container and fails the engine's own strict lint (no golden test uses a trust boundary); then remove the tolerance in `docs/diagrams/build.sh`. (b) Run `build.sh --check` in CI: needs a read token for the private claude-skills repo, or the engine published as a package. | Keep the diagrams honest without relying on people remembering to regenerate them. | `tests/golden/`, `.github/workflows/validate.yml` | S | open |

### Not to copy

The contexts and taxonomy, `export_context.py` and private-skill handling of claude-skills exist to keep work content
separate from personal content across several plugins. The factory is a single toolkit, so they would only add work.

---

## Order of work

### Phase 1: shared services foundation (now)

| Step | Items | Status |
|---|---|---|
| 1. Versioning and releases (tag `v1`) | I3, I4 | done (#2, #4); `v1.0.0` released, `v1` created |
| 2. Move the Claude review, mentions and content guard into the factory as shared services | I2, I5, I9 | done (#2) |
| 3. Switch claude-skills to the shared services, replacing its own copies | | open: `v1.0.0` exists; needs a branch in claude-skills |
| 4. Templates and `/factory-onboard` use the shared services | I2, I5 | done (#2) |

**Step 3 in detail:**
- `claude-code-review.yml` becomes a caller of `reusable-claude-review.yml@v1` (same triggers, `paths-ignore`,
  concurrency and `skip-review` label kept in the caller).
- `claude-mention.yml` becomes a caller of `reusable-claude-mention.yml@v1`.
- `content.yml` becomes a caller of the `content-guard@v1` action. claude-skills keeps its `content-ok` marker and
  denylist, which the shared guard supports unchanged. Its local `scripts/check_content.py` and hooks stay for
  offline use.
- `.claude/skills/pr-review/SKILL.md` stays in claude-skills: it is the project's own checklist.

### Phase 2: confidence in the factory

I6 (validation and script tests, done in #5), I1 (evals), I10 (generated catalog), I13 (I6 follow-ups), I14 (diagrams
from sketches, done), I15 (diagram follow-ups).

### Phase 3: distribution

I7 (plugin marketplace), I8 (link mode), I12 (reuse skills).

---

## Enterprise track

The goal and the reasoning are in [ENTERPRISE-VISION.md](ENTERPRISE-VISION.md); the gaps it closes are drawn in
[capability-gaps](diagrams/capability-gaps.png). **Status of the whole track:
proposed.** It is analysed again, and the open questions in section 7 of the vision are answered, before E1 starts.
Phase 1 to 3 items above continue in parallel; I1 (evals) and I7 (plugin marketplace) are also prerequisites here.

| ID | Item | Phase | Effort | Status |
|---|---|---|---|---|
| E1.1 | **Separate organization and personal setup.** Split `claude/CLAUDE.md` into organization standards and an optional personal layer; remove "About me" from the shared rules; rewrite README and docs for roles (platform team, project teams, architects). | E1 Foundations | S | proposed |
| E1.2 | **Profiles and `factory.yaml`.** Per-project profile (`personal`, `team`, `enterprise`), highest level allowed, models per tier, budget cap per run; `personal` keeps today's behavior. | E1 | M | proposed |
| E1.3 | **Repository governance.** CODEOWNERS per area, rulesets protecting `main`, required reviews, release approval. | E1 | S | proposed |
| E1.4 | **Central distribution.** Plugin marketplace (I7) plus documented managed settings; organization owner in `new-project.sh`. | E1 | M | proposed |
| E1.5 | **Evidence records.** Every pipeline run writes a record (spec, approvals, findings, model, cost) next to the plan. | E1 | M | proposed |
| E1.6 | **Hosting decision.** Public in `egov-sofa`, or GitHub Enterprise with internal repos; settles how claude-skills and teams reach the factory. | E1 | XS (decision) | proposed |
| E2.1 | **Spec Kit-compatible layout.** `standards/` as the constitution; `spec.md` (EARS requirements with IDs), `plan.md` and `tasks.md` per change; living specs for the system. | E2 Spec-driven | M | proposed |
| E2.2 | **Traceability.** Requirement IDs linked to tests, code, ADRs and pull requests; the tester and reviewer check the links. | E2 | M | proposed |
| E2.3 | **Classifier and levels L0 to L3.** A Haiku step proposes the level; the person can override; the pipeline adapts. | E2 | M | proposed |
| E3.1 | **Solution architect agent** (lead): C4 diagrams (reusing claude-skills `architecture-diagram`), ADRs, non-functional requirements. | E3 Design gate | M | proposed |
| E3.2 | **Security architect agent:** STRIDE threat model and security requirements at design time. | E3 | M | proposed |
| E3.3 | **Design gate at L2** with human approval, and an **architecture repository** for principles, ADRs and the technology radar. | E3 | M | proposed |
| E4.1 | **Data and Database architects** with triggers (data flows, schema or migration changes). | E4 Specialists | M | proposed |
| E4.2 | **AI architect** with a trigger (the change calls an LLM or ML model). | E4 | S | proposed |
| E4.3 | **Cloud, Platform and Network architects** with triggers (infrastructure as code, CI/CD, runtime, connectivity). | E4 | M | proposed |
| E5.1 | **Business architect:** capability map, business requirements and KPIs that feed the spec at L3. | E5 Strategic | M | proposed |
| E5.2 | **Enterprise, Information and Technology architects:** principles, information model and classification, technology radar; an L3 architecture review board. | E5 | L | proposed |
| E6.1 | **Evals for every agent and architect** (extends I1), run before each release. | E6 Delivery and trust | M | proposed |
| E6.2 | **Supply chain:** SBOM, signed releases with SLSA provenance, dependency review, licence policy. | E6 | M | proposed |
| E6.3 | **CD and infrastructure-as-code templates:** environments with approvals and a landing zone. | E6 | L | proposed |
| E6.4 | **Model governance and metrics:** approved models, data residency, cost reporting, DORA metrics. | E6 | M | proposed |

---

## Review log

- **2026-11-11:** first review, comparing the factory with `egov-ai/claude-skills`. Decision to make the factory a
  provider of shared, versioned services ([SHARED-SERVICES.md](SHARED-SERVICES.md)). Phase 1 steps 1, 2 and 4 done
  on branch `claude/vigilant-darwin-zn54mk`.
- **2026-11-11:** I6 done on branch `feat/validate-and-test-factory-scripts`: `scripts/validate.py` checks agent and
  skill frontmatter, and `scripts/tests/` runs `install.sh`, `uninstall.sh` and `new-project.sh` in the self-test.
  The tests found and fixed: `install.sh` backed up `CLAUDE.md` on every run, `install.sh` and `uninstall.sh` could
  drop user text when the block markers were broken (they now refuse), `new-project.sh` used GNU-only `sed -i` and
  exited silently when `gh` was missing or logged out, and the pr-review checklist did not list `{{FACTORY_REPO}}`.
- **2026-11-11:** `v1.0.0` released from GitHub with the manual Release workflow (#4); `v1` created. Proposed the
  enterprise track ([ENTERPRISE-VISION.md](ENTERPRISE-VISION.md)): 12 architect roles in three layers, levels L0 to L3
  so cost follows risk, a Spec Kit-compatible spec layout, and phases E1 to E6. To be analysed again before work
  starts.
- **2026-11-11:** I14 done: all diagrams redrawn with the architecture-diagram skill of `egov-ai/claude-skills`
  (0.10.0, `6a715ce`) from YAML sketches in `docs/diagrams/`, and new ones added for the problems (`@main` coupling,
  cross-organization access, capability gaps) and the target (shared services, releases, architect layers, levels,
  spec-driven traceability, enterprise landscape). Found an engine bug with the trust-boundary legend (I15).
