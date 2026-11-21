"""Tests of scripts/build_plugin.py: the plugin `claude plugin eval` runs against (roadmap I1).

Run: python3 -m unittest discover -s scripts/tests
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

import support

sys.path.insert(0, str(support.SCRIPTS))
import build_plugin  # noqa: E402  (after the sys.path line above)


class RealBuild(unittest.TestCase):
    """The factory as it is, built once for all the tests of this class."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.plugin = build_plugin.build(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_manifest(self):
        manifest = json.loads((self.plugin / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("software-factory", manifest["name"])
        self.assertEqual({"evals": "evals"}, manifest["experimental"])
        self.assertTrue(manifest["description"])
        # a release tag, never the moving v1 tag; a commit or "unknown" without one
        self.assertRegex(manifest["version"], r"^(v\d+\.\d+\.\d+(-\d+-g[0-9a-f]+)?|[0-9a-f]{7,}|unknown)$")

    def test_contents(self):
        for rel in ("agents/reviewer.md", "agents/tester.md", "skills/factory-review/SKILL.md",
                    "claude/hooks/agent_guard.py", "standards/SECURITY.md", "evals/_probe/case.yaml"):
            with self.subTest(rel):
                self.assertTrue((self.plugin / rel).is_file())
        self.assertFalse(list(self.plugin.rglob("__pycache__")))

    def test_no_placeholder_left_and_paths_point_into_the_build(self):
        self.assertEqual([], build_plugin.leftovers(self.plugin))
        reviewer = (self.plugin / "agents" / "reviewer.md").read_text(encoding="utf-8")
        self.assertIn(f"{self.plugin.as_posix()}/standards/DEFINITION-OF-DONE.md", reviewer)

    def test_plugin_level_guard(self):
        """The fallback the probe made necessary: one PreToolUse hook for every tool call, on the agents' matcher."""
        raw = (self.plugin / "hooks" / "hooks.json").read_bytes()
        self.assertNotIn(b"\r\n", raw)
        (entry,) = json.loads(raw)["hooks"]["PreToolUse"]
        tester = (support.FACTORY / "claude" / "agents" / "tester.md").read_text(encoding="utf-8")
        self.assertIn(f'matcher: "{entry["matcher"]}"', tester)
        (hook,) = entry["hooks"]
        self.assertEqual("command", hook["type"])
        self.assertIn('"${CLAUDE_PLUGIN_ROOT}/claude/hooks/agent_guard.py" --agent-from-input', hook["command"])
        self.assertTrue(hook["command"].startswith('PY=python3; "$PY" -c "" 2>/dev/null || PY=python;'))


class FakeRoot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "factory"
        for rel, text in (("claude/agents/a.md", "see {{FACTORY_HOME}}/standards/X.md\n"),
                          ("claude/skills/s/SKILL.md", "skill\n"), ("claude/hooks/agent_guard.py", "# guard\n"),
                          ("standards/X.md", "x\n"), ("evals/c/case.yaml", "name: c\n"),
                          ("evals/results/2026/result.json", "{}\n")):
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
        self.out = Path(self.tmp.name) / "out"

    def tearDown(self):
        self.tmp.cleanup()

    def test_results_are_not_copied(self):
        plugin = build_plugin.build(self.out, root=self.root)
        self.assertTrue((plugin / "evals" / "c" / "case.yaml").is_file())
        self.assertFalse((plugin / "evals" / "results").exists())

    def test_placeholder_is_filled(self):
        plugin = build_plugin.build(self.out, root=self.root)
        text = (plugin / "agents" / "a.md").read_text(encoding="utf-8")
        self.assertEqual(f"see {plugin.as_posix()}/standards/X.md\n", text)

    def test_a_placeholder_left_is_an_error(self):
        # a file type render() does not fill
        (self.root / "standards" / "data.bin").write_bytes(b"{{FACTORY_HOME}}")
        with self.assertRaisesRegex(build_plugin.BuildError, re.escape("standards/data.bin")):
            build_plugin.build(self.out, root=self.root)

    def test_a_second_build_replaces_the_first(self):
        build_plugin.build(self.out, root=self.root)
        (self.root / "standards" / "X.md").unlink()
        plugin = build_plugin.build(self.out, root=self.root)
        self.assertFalse((plugin / "standards" / "X.md").exists())


if __name__ == "__main__":
    unittest.main()
