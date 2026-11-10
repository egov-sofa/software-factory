---
name: factory-new
description: Scaffold a new project from a software-factory template (typescript, python, generic), with tests, lint, CI and CLAUDE.md preconfigured. Optionally creates the GitHub repo.
argument-hint: "<project-name> [typescript|python|generic]"
---

# Factory New Project

Arguments: $ARGUMENTS
Factory location: `{{FACTORY_HOME}}`

1. **Gather the inputs.** You need: a project name (lowercase-kebab-case), a template, and a GitHub choice (none / private / public).
   - Available templates: list the folders in `{{FACTORY_HOME}}/templates/` (except `_shared`), and read the top of each one's `README.md`.
   - If the template is missing, recommend one based on what the user wants to build, in one sentence: web, API or CLI in JS → `typescript`; data, AI or scripting → `python`; anything else → `generic`.
   - Ask about GitHub using the AskUserQuestion tool if it wasn't specified. Creating a repo is visible to others (when public), so always ask.
2. **Run the scaffolder:**
   ```bash
   bash "{{FACTORY_HOME}}/scripts/new-project.sh" <name> <template> [--github private|public]
   ```
   Projects go in `~/projects/` by default. Add `--dir <path>` if the user wants somewhere else.
3. **Install and verify.** `cd` into the project and run its install and test commands (they're listed in the new project's `CLAUDE.md`). Report the results honestly.
4. **Explain what was created**, as a short annotated tree of the key files and what each one is for.
5. **Next steps:** `cd <path> && claude`, then `/factory-build <first feature>`.
