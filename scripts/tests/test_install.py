"""Tests of scripts/install.sh and scripts/uninstall.sh, run with bash into a temporary CLAUDE_CONFIG_DIR.

The scripts only read the factory, so they run from the real checkout. Run: python3 -m unittest discover -s scripts/tests
"""
import tempfile
import unittest
from pathlib import Path

from support import FACTORY, SCRIPTS, needs_bash, posix, run

START = "<!-- software-factory:start -->"
END = "<!-- software-factory:end -->"
USER_TEXT = "# My own rules\n\n- Always answer in French.\n"

# Layouts of CLAUDE.md whose markers are broken; replacing or removing "the block" could drop user content.
BROKEN = {
    "start without end": f"{USER_TEXT}\n{START}\nfactory text\nmore of my own rules\n",
    "end without start": f"{USER_TEXT}\nfactory text\n{END}\nmore of my own rules\n",
    "end before start": f"{USER_TEXT}\n{END}\nmine\n{START}\nmore of my own rules\n",
    "two start markers": f"{USER_TEXT}\n{START}\nold\n{START}\nnew\n{END}\nmine\n",
    "two blocks": f"{START}\na\n{END}\n{USER_TEXT}\n{START}\nb\n{END}\n",
    "marker inside a line": f"{USER_TEXT}\nsee {START}\nfactory text\n{END}\nmine\n",
}


def factory_files():
    """Paths, relative to the Claude config folder, of every agent and skill file the factory installs."""
    agents = [f"agents/{p.name}" for p in sorted((FACTORY / "claude" / "agents").glob("*.md"))]
    skills = [f"skills/{p.parent.name}/{p.name}" for p in sorted((FACTORY / "claude" / "skills").glob("*/*"))
              if p.is_file()]
    return agents + skills


@needs_bash
class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "claude-config"
        self.claude_md = self.dir / "CLAUDE.md"

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, *args):
        return run(SCRIPTS / "install.sh", *args, env={"CLAUDE_CONFIG_DIR": posix(self.dir)})

    def uninstall(self):
        return run(SCRIPTS / "uninstall.sh", env={"CLAUDE_CONFIG_DIR": posix(self.dir)})

    def installed(self):
        result = self.install()
        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        return result

    def write_claude_md(self, text):
        self.dir.mkdir(parents=True, exist_ok=True)
        self.claude_md.write_bytes(text.encode("utf-8"))

    def backups(self, rel):
        """Contents of every backup of one file, oldest folder first."""
        return [p.read_text(encoding="utf-8") for p in sorted((self.dir / "backups").glob(f"software-factory-*/{rel}"))]


class Install(Base):
    def test_fresh_install(self):
        self.installed()
        for rel in factory_files():
            with self.subTest(rel):
                text = (self.dir / rel).read_text(encoding="utf-8")
                self.assertNotIn("{{FACTORY_HOME}}", text)
        text = self.claude_md.read_text(encoding="utf-8")
        self.assertEqual(1, text.splitlines().count(START))
        self.assertEqual(1, text.splitlines().count(END))
        self.assertNotIn("{{FACTORY_HOME}}", text)
        reviewer = (self.dir / "agents" / "reviewer.md").read_text(encoding="utf-8")
        self.assertIn(f"{FACTORY.as_posix()}/standards/".lower(), reviewer.lower())
        self.assertFalse((self.dir / "backups").exists())

    def test_user_content_kept_and_backed_up(self):
        self.write_claude_md(USER_TEXT)
        self.installed()
        text = self.claude_md.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(USER_TEXT), text[:200])
        self.assertEqual(1, text.splitlines().count(START))
        self.assertEqual([USER_TEXT], self.backups("CLAUDE.md"))

    def test_second_run_is_idempotent(self):
        self.write_claude_md(USER_TEXT)
        self.installed()
        before = self.claude_md.read_bytes()
        backups = sorted(p.relative_to(self.dir) for p in (self.dir / "backups").rglob("*") if p.is_file())
        result = self.installed()
        status = [line for line in result.stdout.splitlines() if line[:4] in ("  = ", "  ~ ", "  + ")]
        self.assertEqual(len(factory_files()) + 1, len(status), result.stdout)
        for line in status:
            self.assertTrue(line.endswith("(unchanged)"), line)
        self.assertEqual(before, self.claude_md.read_bytes())
        self.assertEqual(backups, sorted(p.relative_to(self.dir) for p in (self.dir / "backups").rglob("*")
                                         if p.is_file()))

    def test_old_block_is_replaced_not_duplicated(self):
        self.installed()
        lines = self.claude_md.read_text(encoding="utf-8").splitlines()
        lines.insert(lines.index(START) + 1, "an old factory rule")
        old = "\n".join([USER_TEXT, *lines, "", "# After the block", "my closing rule", ""])
        self.write_claude_md(old)
        result = self.installed()
        self.assertIn("factory block updated", result.stdout)
        text = self.claude_md.read_text(encoding="utf-8")
        self.assertEqual(1, text.splitlines().count(START))
        self.assertNotIn("an old factory rule", text)
        self.assertTrue(text.startswith(USER_TEXT))
        self.assertTrue(text.endswith("# After the block\nmy closing rule\n"), text[-200:])
        self.assertIn(old, self.backups("CLAUDE.md"))

    def test_edited_agent_is_restored_and_backed_up(self):
        self.installed()
        agent = self.dir / "agents" / "reviewer.md"
        original = agent.read_bytes()
        agent.write_text("edited by hand\n", encoding="utf-8")
        result = self.installed()
        self.assertIn("+ agents/reviewer.md", result.stdout)
        self.assertEqual(original, agent.read_bytes())
        self.assertIn("edited by hand\n", self.backups("agents/reviewer.md"))

    def test_dry_run_writes_nothing(self):
        result = self.install("--dry-run")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(self.dir.exists())

    def test_broken_markers_are_refused(self):
        for label, text in BROKEN.items():
            with self.subTest(label):
                self.write_claude_md(text)
                for args in ((), ("--dry-run",)):
                    result = self.install(*args)
                    self.assertEqual(1, result.returncode, result.stdout)
                    self.assertIn("CLAUDE.md has broken software-factory markers", result.stderr)
                    self.assertIn("Nothing was changed", result.stderr)
                    self.assertEqual(text.encode("utf-8"), self.claude_md.read_bytes())
                self.assertEqual(["CLAUDE.md"], sorted(p.name for p in self.dir.iterdir()))


class Uninstall(Base):
    def test_removes_factory_files_keeps_user_files(self):
        self.write_claude_md(USER_TEXT)
        self.installed()
        mine = self.dir / "agents" / "mine.md"
        mine.write_text("my agent\n", encoding="utf-8")
        result = self.uninstall()
        self.assertEqual(0, result.returncode, result.stderr)
        for rel in factory_files():
            with self.subTest(rel):
                self.assertFalse((self.dir / rel).exists())
        self.assertEqual("my agent\n", mine.read_text(encoding="utf-8"))
        text = self.claude_md.read_text(encoding="utf-8")
        self.assertIn(USER_TEXT, text)
        self.assertNotIn(START, text)
        self.assertNotIn(END, text)

    def test_deletes_claude_md_when_only_block(self):
        self.installed()
        result = self.uninstall()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(self.claude_md.exists())

    def test_broken_markers_are_refused(self):
        self.installed()
        for label, text in BROKEN.items():
            with self.subTest(label):
                self.write_claude_md(text)
                result = self.uninstall()
                self.assertEqual(1, result.returncode, result.stdout)
                self.assertIn("CLAUDE.md has broken software-factory markers", result.stderr)
                self.assertIn("Nothing was removed", result.stderr)
                self.assertEqual(text.encode("utf-8"), self.claude_md.read_bytes())
                self.assertFalse((self.dir / "CLAUDE.md.tmp").exists())
                for rel in factory_files():
                    self.assertTrue((self.dir / rel).exists(), rel)


if __name__ == "__main__":
    unittest.main()
