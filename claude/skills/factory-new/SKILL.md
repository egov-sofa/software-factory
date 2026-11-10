---
name: factory-new
description: Scaffold a new project from a software-factory template (typescript, python, generic), with tests, lint, CI and CLAUDE.md preconfigured. Asks which GitHub org owns it; optionally creates the GitHub repo.
argument-hint: "<project-name> [typescript|python|generic] [owner]"
---

# Factory New Project

Arguments: $ARGUMENTS
Factory location: `{{FACTORY_HOME}}`

1. **Gather the inputs.** You need: a project name (lowercase-kebab-case), a template, an **owner**, and a GitHub choice (none / private / public).
   - Available templates: list the folders in `{{FACTORY_HOME}}/templates/` (except `_shared`), and read the top of each one's `README.md`.
   - If the template is missing, recommend one based on what the user wants to build, in one sentence: web, API or CLI in JS → `typescript`; data, AI or scripting → `python`; anything else → `generic`.
   - **Owner: always ask** with the AskUserQuestion tool, unless it was given in the arguments. Never pick one yourself. Get the choices from `gh api user/orgs -q '.[].login'` plus the personal login (`gh api user -q .login`). The owner decides both the GitHub org and the local folder.
   - Ask about GitHub (none / private / public) with AskUserQuestion if it wasn't specified. Creating a repo is visible to others, so always ask.
2. **Run the scaffolder:**
   ```bash
   bash "{{FACTORY_HOME}}/scripts/new-project.sh" <name> <template> --owner <owner> [--github private|public]
   ```
   The project is created at `<workspace>/<owner>/<name>`. The workspace is the folder that holds the org folders (for example `egov-rdc/egov-ai/<name>`). Add `--dir <path>` only if the user wants somewhere else.
3. **Install and verify.** `cd` into the project and run its install and test commands (they're listed in the new project's `CLAUDE.md`). Report the results honestly.
4. **Explain what was created**, as a short annotated tree of the key files and what each one is for.
5. **Next steps:** `cd <path> && claude`, then `/factory-build <first feature>`.
