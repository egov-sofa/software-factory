# Diagrams

Every diagram in the factory's documentation is drawn by the **architecture-diagram** skill of
[`egov-ai/claude-skills`](https://github.com/egov-ai/claude-skills) (version 0.10.0, commit `6a715ce`), in its house
style. Each one has three files here:

| File | What it is |
|---|---|
| `<name>.yaml` | **The source:** a short sketch of what the diagram shows. Edit this file. |
| `<name>.drawio` | Generated from the sketch. Open it in draw.io to look, never to edit. |
| `<name>.png` | Exported from the `.drawio` with the draw.io CLI. This is what the docs embed. A file with several pages gives `<name>-1.png`, `<name>-2.png`... |

The `.svg` exports are git-ignored, like in claude-skills.

## Index

| Diagram | Shows | Notation | Used in |
|---|---|---|---|
| [factory-overview](factory-overview.png) | The four parts and how they connect: repo, scripts, your machine, projects | C4 | README, [HOW-IT-WORKS](../HOW-IT-WORKS.md), [GETTING-STARTED](../GETTING-STARTED.md) |
| [factory-build-pipeline](factory-build-pipeline.png) | `/factory-build` as a process: plan, your approval, build, test, review, fix loop, docs | BPMN | [HOW-IT-WORKS](../HOW-IT-WORKS.md), Part 1 |
| [project-scaffolding](project-scaffolding.png) | How `new-project.sh` layers templates, fills placeholders and turns the hooks on | C4 | [HOW-IT-WORKS](../HOW-IT-WORKS.md), Part 2 |
| [shared-services](shared-services.png) | Thin callers in projects, logic in the factory at `v1`, the pull request as an untrusted zone | C4, trust boundary | [HOW-IT-WORKS](../HOW-IT-WORKS.md) Part 3, [SHARED-SERVICES](../SHARED-SERVICES.md) |
| [rules-and-standards](rules-and-standards.png) | Where Claude's rules come from and which one wins | C4 | [HOW-IT-WORKS](../HOW-IT-WORKS.md), Part 4 |
| [claude-services-auth](claude-services-auth-1.png) | How a review run gets a short-lived token ([1](claude-services-auth-1.png)) and how a repository is set up, in the Console or with the script ([2](claude-services-auth-2.png)) | C4 | [CLAUDE-SERVICES-AUTH](../CLAUDE-SERVICES-AUTH.md), [SHARED-SERVICES](../SHARED-SERVICES.md) |
| [version-pinning](version-pinning.png) | **Problem and fix:** projects followed `main`; now they follow `v1` | C4 change diagram | [SHARED-SERVICES](../SHARED-SERVICES.md), [CUSTOMIZING](../CUSTOMIZING.md) |
| [release-flow](release-flow.png) | How a release is made and reaches projects | BPMN | [SHARED-SERVICES](../SHARED-SERVICES.md), [CUSTOMIZING](../CUSTOMIZING.md) |
| [cross-org-access](cross-org-access-1.png) | **Problem and options:** a public factory today ([1](cross-org-access-1.png)), what breaks if it were private ([2](cross-org-access-2.png)), one GitHub Enterprise ([3](cross-org-access-3.png)) | C4 | [SHARED-SERVICES](../SHARED-SERVICES.md), [CUSTOMIZING](../CUSTOMIZING.md), [ENTERPRISE-VISION](../ENTERPRISE-VISION.md) |
| [capability-gaps](capability-gaps.png) | **Problem:** the gap between today's factory and enterprise grade, as heat | Capability map | [ENTERPRISE-VISION](../ENTERPRISE-VISION.md), [ROADMAP](../ROADMAP.md) |
| [enterprise-landscape](enterprise-landscape.png) | **Target:** marketplace, managed settings, architecture repository, evidence | C4, planned | [ENTERPRISE-VISION](../ENTERPRISE-VISION.md) |
| [architect-layers](architect-layers.png) | The twelve architect roles in three layers, and who triggers whom | ArchiMate | [ENTERPRISE-VISION](../ENTERPRISE-VISION.md) |
| [rigour-levels](rigour-levels.png) | Levels L0 to L3: who is involved at each level | BPMN | [ENTERPRISE-VISION](../ENTERPRISE-VISION.md) |
| [sdd-traceability](sdd-traceability.png) | Spec-driven development: today's single plan versus spec, plan, tasks and evidence | C4 change view | [ENTERPRISE-VISION](../ENTERPRISE-VISION.md) |

## Change a diagram

1. Edit `<name>.yaml`. The vocabulary is in claude-skills: `skills/architecture/architecture-diagram/references/`
   (`sketch-format.md` first, then the notation file: `notation-c4.md`, `notation-bpmn.md`, `notation-capability.md`).
2. Regenerate it:
   ```bash
   bash docs/diagrams/build.sh <name>
   ```
3. Open the PNG and look at it before committing. The engine routes the edges, but a second pass is normal: reorder
   items, add a `spacer`, or set `ports` on one edge. Never edit the `.drawio` or `.png` by hand.
4. Commit the `.yaml`, `.drawio` and `.png` together.

**A change diagram** (`version-pinning`) has two inputs, `<name>.before.yaml` and `<name>.after.yaml`. `build.sh`
runs the engine's `sketch_diff.py` on them to write `<name>.yaml`, which marks what is new, changed and removed. Edit the
two inputs, never the output.

**Check that every committed diagram matches its sketch** (no PNG export, so no draw.io needed):
```bash
bash docs/diagrams/build.sh --check
```

## What build.sh needs

- Python 3 with PyYAML.
- A clone of `egov-ai/claude-skills`. By default `build.sh` looks next to the factory's org folder
  (`<workspace>/egov-ai/claude-skills`); set `CLAUDE_SKILLS=/path/to/claude-skills` otherwise.
- For the PNG export, the draw.io desktop CLI at the version claude-skills pins in
  `skills/architecture/architecture-diagram/tests/golden/DRAWIO_VERSION` (32.6.1 today). On Linux without a display
  it runs under `xvfb-run`. claude-skills' `validate.yml` shows how to install it with a checksum check.

CI does not check the diagrams yet: claude-skills is private and lives in another organization, so the factory's
workflows cannot clone it without a token (roadmap I15).

## Known engine issue

architecture-diagram 0.10.0 draws the legend sample of a **trust boundary** as an empty container, and its own strict
lint then reports it (`W legend-b3: container without children`). None of the engine's golden tests uses a trust
boundary, so its CI does not see it. `build.sh` tolerates exactly this one warning, prints a note when it does, and
fails on any other warning. Remove the filter in `build.sh` once the engine is fixed (roadmap I15).
