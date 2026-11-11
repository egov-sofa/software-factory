"""Tests of scripts/validate.py, the frontmatter check of the factory's agents and skills.

Run: python3 -m unittest discover -s scripts/tests
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "validate.py"
sys.path.insert(0, str(SCRIPT.parent))
import validate  # noqa: E402  (after the sys.path line above)

AGENT = """---
name: helper
description: Helps.
tools: Read, Grep
model: sonnet
---

Body.
"""

SKILL = """---
name: do-thing
description: Does the thing.
argument-hint: "<what>"
---

Body.
"""


class Frontmatter(unittest.TestCase):
    def agent(self, text, name="helper"):
        return validate.check(text, "agent", name)

    def skill(self, text, name="do-thing"):
        return validate.check(text, "skill", name)

    def test_repository_is_valid(self):
        count, found = validate.validate(validate.ROOT)
        self.assertEqual([], found)
        self.assertGreater(count, 10)

    def test_valid_files(self):
        self.assertEqual([], self.agent(AGENT))
        self.assertEqual([], self.skill(SKILL))

    def test_each_problem_is_reported(self):
        cases = {
            "no opening marker": (self.agent("name: helper\n"), 1, "no frontmatter"),
            "no closing marker": (self.agent("---\nname: helper\ndescription: x\n"), 1, "no closing '---'"),
            "missing name": (self.agent(AGENT.replace("name: helper\n", "")), 1, "missing 'name'"),
            "missing description": (self.agent(AGENT.replace("description: Helps.\n", "")), 1,
                                    "missing 'description'"),
            "empty description": (self.agent(AGENT.replace("Helps.", '""')), 3, "empty 'description'"),
            "agent name": (self.agent(AGENT, name="other"), 2, "does not match the file name 'other'"),
            "skill name": (self.skill(SKILL, name="other"), 2, "does not match the folder name 'other'"),
            "model": (self.agent(AGENT.replace("sonnet", "claude-opus-4")), 5, "model 'claude-opus-4' is not one of"),
            "unknown tool": (self.agent(AGENT.replace("Grep", "Grpe")), 4, "unknown tool 'Grpe' in tools"),
            "unknown allowed tool": (self.skill(SKILL.replace("---\n\n", "allowed-tools: Read, Fetch\n---\n\n")), 5,
                                     "unknown tool 'Fetch' in allowed-tools"),
            "unknown key": (self.agent(AGENT.replace("tools:", "tool:")), 4, "unknown frontmatter key 'tool'"),
            "agent key on a skill": (self.skill(SKILL.replace("---\n\n", "tools: Read\n---\n\n")), 5,
                                     "unknown frontmatter key 'tools' for a skill"),
            "folded value": (self.agent(AGENT.replace("Helps.", ">")), 3, "unsupported frontmatter syntax"),
            "stray line": (self.agent(AGENT.replace("model:", "just text\nmodel:")), 5,
                           "unsupported frontmatter syntax"),
            "read-only with Write": (self.agent(AGENT.replace("name: helper", "name: reviewer")
                                                .replace("Grep", "Write"), name="reviewer"), 4,
                                     "read-only agent has the write tool 'Write'"),
            "read-only with a rule": (self.agent(AGENT.replace("name: helper", "name: reviewer")
                                                 .replace("Grep", "Edit(src/*)"), name="reviewer"), 4,
                                      "read-only agent has the write tool 'Edit(src/*)'"),
            "read-only without tools": (self.agent(AGENT.replace("name: helper", "name: security-auditor")
                                                   .replace("tools: Read, Grep\n", ""), name="security-auditor"), 1,
                                        "read-only agent without 'tools'"),
        }
        for label, (found, line, message) in cases.items():
            with self.subTest(label):
                self.assertTrue(any(num == line and message in text for num, text in found), found)

    def test_tools_formats(self):
        formats = {
            "string": "tools: Read, Grep, Bash",
            "spaces": "tools: Read Grep Bash",
            "inline list": "tools: [Read, \"Grep\", Bash]",
            "block list": "tools:\n  - Read\n  - Grep\n  - Bash",
            "mcp": "tools: Read, mcp__github__create_issue, mcp__slack",
            "rule": "tools: Read, Bash(git status:*), Bash(npm run test:*)",
        }
        for label, line in formats.items():
            with self.subTest(label):
                self.assertEqual([], self.agent(AGENT.replace("tools: Read, Grep", line)))
        fields, _ = validate.frontmatter(AGENT.replace("tools: Read, Grep", formats["block list"]))
        self.assertEqual(["Read", "Grep", "Bash"], validate.split_tools(fields["tools"][0]))
        self.assertEqual(["Read", "Bash(git status:*)"], validate.split_tools("Read, Bash(git status:*)"))
        self.assertEqual(["Bash(rm *)"], validate.split_tools("Bash(rm *)"))
        self.assertIsNone(validate.tool_name("Fetch(x)"))

    def test_read_only_agent_with_empty_tools(self):
        """An empty `tools:` is YAML null, which Claude Code treats like no tools field: every tool, the write ones
        too. A read-only agent must not get through with it."""
        reviewer = AGENT.replace("name: helper", "name: reviewer")
        found = self.agent(reviewer.replace("tools: Read, Grep", "tools:"), name="reviewer")
        self.assertTrue(any("read-only agent" in text for _, text in found), found)

    def test_stdlib_only(self):
        """The validator runs on a bare Python in CI and on any machine: it may import the standard library only."""
        import ast
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                modules.add((node.module or "").split(".")[0])
        self.assertEqual(set(), modules - set(sys.stdlib_module_names))

    def test_messages_never_hold_other_content(self):
        found = self.agent(AGENT.replace("model: sonnet", "model: sonnet\nsecret_key: s3cr3t-value"))
        self.assertEqual([(6, "unknown frontmatter key 'secret_key' for an agent")], found)


class CommandLine(unittest.TestCase):
    """The validator run as a command on a fake factory tree, as CI runs it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.write("claude/agents/helper.md", AGENT)
        self.write("claude/skills/do-thing/SKILL.md", SKILL)
        self.write("templates/_shared/.claude/skills/do-thing/SKILL.md", SKILL)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def validate(self, *args):
        return subprocess.run([sys.executable, "-I", str(SCRIPT), *args], check=False, capture_output=True,
                              text=True)

    def test_clean_tree_passes(self):
        result = self.validate("--root", str(self.root))
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("No problems in 3 file(s).", result.stdout)

    def test_problems_fail_with_locations(self):
        self.write(".claude/skills/review/SKILL.md", SKILL)
        self.write("claude/agents/helper.md", AGENT.replace("sonnet", "gpt"))
        result = self.validate("--root", str(self.root))
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("claude/agents/helper.md:5: model 'gpt' is not one of", result.stdout)
        self.assertIn(".claude/skills/review/SKILL.md:2: name 'do-thing' does not match the folder name 'review'",
                      result.stdout)
        self.assertIn("2 problem(s) in 4 file(s).", result.stdout)

    def test_bad_argument_is_a_usage_error(self):
        for args in (["--bogus"], ["--root"], ["--root", str(self.root / "missing")]):
            with self.subTest(args=args):
                result = self.validate(*args)
                self.assertEqual(2, result.returncode)
                self.assertIn("Exit code 0", result.stderr)


if __name__ == "__main__":
    unittest.main()
