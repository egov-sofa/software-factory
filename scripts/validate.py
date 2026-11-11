#!/usr/bin/env python3
"""Check the frontmatter of the factory's agents and skills, so a typo turns the self-test red instead of making
Claude Code silently ignore an agent, a model or a tool.

What is checked:
  claude/agents/*.md                       agents installed by scripts/install.sh
  claude/skills/*/SKILL.md                 skills installed by scripts/install.sh
  .claude/skills/*/SKILL.md                the factory's own project skills (pr-review)
  templates/*/.claude/skills/*/SKILL.md    skills copied into every new project

Rules: the file starts with a frontmatter block between two '---' lines; `name` and a non-empty `description` are
present; `name` matches the file name (agents) or the folder name (skills); `model`, if present, is one of MODELS;
`tools` (agents) and `allowed-tools` (skills) name only known Claude Code tools, MCP tools (mcp__server__tool) or
permission rules on a known tool (Bash(git status:*)); every key is a known one; the read-only agents declare `tools`
and never get a tool that writes files.

The frontmatter reader handles what the factory uses: `key: value` (quoted or not), inline lists `[a, b]` and block
lists (`- item` lines). Anything else, such as folded `>` values, is reported instead of guessed.

Options:
  --root DIR    the tree to check (default: the factory this script sits in)

Exit code 0 if nothing is found, 1 if something is found, 2 on a usage error.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The aliases the review checklist allows; a full model ID would break at the next model release.
MODELS = ("opus", "sonnet", "haiku", "inherit")
KNOWN_TOOLS = {
    "Agent", "Task", "Bash", "BashOutput", "KillShell", "Edit", "MultiEdit", "Write", "Read", "Glob", "Grep", "LS",
    "NotebookEdit", "NotebookRead", "TodoWrite", "WebFetch", "WebSearch", "Skill", "SlashCommand", "AskUserQuestion",
    "ExitPlanMode",
}
# Known keys only, so `tool:` instead of `tools:` is caught. Extend these when Claude Code adds a field.
AGENT_KEYS = {"name", "description", "tools", "disallowedTools", "model", "color", "permissionMode", "skills",
              "mcpServers"}
SKILL_KEYS = {"name", "description", "allowed-tools", "argument-hint", "model", "disable-model-invocation",
              "user-invocable", "license", "context", "agent"}
READ_ONLY_AGENTS = {"reviewer", "security-auditor"}
WRITE_TOOLS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}

KEY_RE = re.compile(r"([A-Za-z][\w-]*):(?:\s+(.*))?$")
ITEM_RE = re.compile(r"\s*-\s+(.*)$")
MCP_RE = re.compile(r"mcp__[\w-]+(?:__[\w-]+)?$")
RULE_RE = re.compile(r"(\w+)\(.*\)$")


def unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def frontmatter(text):
    """(fields, problems): fields maps a key to (value, line number), or is None without a frontmatter block; a value
    is a string or a list of strings. Problems are (line number, message) pairs."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, [(1, "no frontmatter (the file must start with a '---' line)")]
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return None, [(1, "no frontmatter (no closing '---' line)")]
    fields, problems, current = {}, [], None
    for num in range(2, end + 1):   # 1-based numbers of the lines between the markers
        line = lines[num - 1]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = ITEM_RE.match(line)
        if item and current is not None and isinstance(fields[current][0], list):
            fields[current][0].append(unquote(item.group(1)))
            continue
        m = KEY_RE.match(line)
        if not m:
            problems.append((num, "unsupported frontmatter syntax"))
            current = None
            continue
        key, raw = m.group(1), (m.group(2) or "").strip()
        if key in fields:
            problems.append((num, f"duplicate key '{key}'"))
        if raw[:1] in (">", "|"):
            problems.append((num, f"unsupported frontmatter syntax for '{key}' (write the value on one line)"))
            value = ""
        elif raw.startswith("[") and raw.endswith("]"):
            value = [unquote(v) for v in raw[1:-1].split(",") if v.strip()]
        elif raw == "":
            value = []   # a block list may follow; an empty scalar reads as an empty list
        else:
            value = unquote(raw)
        fields[key] = (value, num)
        current = key
    return fields, problems


def split_tools(value):
    """Tool names from a list or from a string separated by commas or spaces; a permission rule such as
    Bash(git status:*) stays in one piece."""
    if isinstance(value, list):
        return [v.strip() for v in value if v.strip()]
    tools, depth, word = [], 0, ""
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
        if depth == 0 and (ch == "," or ch.isspace()):
            if word:
                tools.append(word)
            word = ""
        else:
            word += ch
    if word:
        tools.append(word)
    return tools


def tool_name(tool):
    """The base tool of an entry (Bash for Bash(git:*)), or None if the entry is not a known tool."""
    if MCP_RE.match(tool):
        return tool
    rule = RULE_RE.match(tool)
    base = rule.group(1) if rule else tool
    return base if base in KNOWN_TOOLS else None


def check(text, kind, expected_name):
    """Problems in one agent ("agent") or skill ("skill") file, as (line number, message) pairs."""
    fields, problems = frontmatter(text)
    if fields is None:
        return problems
    allowed = AGENT_KEYS if kind == "agent" else SKILL_KEYS
    article = "an" if kind == "agent" else "a"
    tools_key = "tools" if kind == "agent" else "allowed-tools"
    for key, (_, num) in fields.items():
        if key not in allowed:
            problems.append((num, f"unknown frontmatter key '{key}' for {article} {kind}"))

    name, name_line = fields.get("name", (None, 1))
    if name is None:
        problems.append((1, "missing 'name'"))
    elif name != expected_name:
        where = "file name" if kind == "agent" else "folder name"
        problems.append((name_line, f"name '{name}' does not match the {where} '{expected_name}'"))
    description, description_line = fields.get("description", (None, 1))
    if description is None:
        problems.append((1, "missing 'description'"))
    elif not description:
        problems.append((description_line, "empty 'description'"))

    if "model" in fields:
        model, num = fields["model"]
        if model not in MODELS:
            problems.append((num, f"model '{model}' is not one of {', '.join(MODELS)}"))

    tools = []
    if tools_key in fields:
        value, num = fields[tools_key]
        tools = split_tools(value)
        for tool in tools:
            if tool_name(tool) is None:
                problems.append((num, f"unknown tool '{tool}' in {tools_key}"))
    if kind == "agent" and expected_name in READ_ONLY_AGENTS:
        # An empty `tools:` (or `tools: []`) is treated by Claude Code like a missing one: every tool.
        if not tools:
            num = fields[tools_key][1] if tools_key in fields else 1
            problems.append((num, "read-only agent without 'tools' (it would get every tool, the write tools too)"))
        else:
            for tool in tools:
                if tool_name(tool) in WRITE_TOOLS:
                    problems.append((fields[tools_key][1], f"read-only agent has the write tool '{tool}'"))
    return sorted(problems)


def targets(root):
    """(path, kind, expected name) for every agent and skill file under root."""
    for path in sorted((root / "claude" / "agents").glob("*.md")):
        yield path, "agent", path.stem
    patterns = ("claude/skills/*/SKILL.md", ".claude/skills/*/SKILL.md", "templates/*/.claude/skills/*/SKILL.md")
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            yield path, "skill", path.parent.name


def validate(root):
    """(number of files checked, problems as 'path:line: message' strings)."""
    count, found = 0, []
    for path, kind, expected in targets(root):
        count += 1
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (UnicodeDecodeError, OSError) as e:
            found.append(f"{rel}:1: cannot read the file ({e.__class__.__name__})")
            continue
        found += [f"{rel}:{num}: {message}" for num, message in check(text, kind, expected)]
    return count, found


def main(argv):
    root = ROOT
    if argv in (["-h"], ["--help"]):
        print(__doc__)
        return 0
    if argv:
        if len(argv) != 2 or argv[0] != "--root" or not Path(argv[1]).is_dir():
            print(__doc__, file=sys.stderr)
            return 2
        root = Path(argv[1]).resolve()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    count, found = validate(root)
    for line in found:
        print(line)
    if found:
        print(f"\n{len(found)} problem(s) in {count} file(s).")
        return 1
    print(f"No problems in {count} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
