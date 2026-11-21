"""Tests of scripts/release-check.sh: a release must move forward, so the major tag (v1) never goes back to older code.

Run: python3 -m unittest discover -s scripts/tests
"""
import tempfile
import unittest
from pathlib import Path

import support

SCRIPT = support.SCRIPTS / "release-check.sh"


@support.needs_bash
class ReleaseCheck(unittest.TestCase):
    """A throwaway repository with three commits: v1.0.0 and v1 on the second."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        support.git(self.repo, "init", "-q", "-b", "main")
        self.commits = []
        for n in range(3):
            support.git(self.repo, "commit", "-q", "--allow-empty", "-m", f"chore: {n}")
            self.commits.append(support.git(self.repo, "rev-parse", "HEAD").strip())
        support.git(self.repo, "tag", "v1.0.0", self.commits[1])
        support.git(self.repo, "tag", "v1", self.commits[1])

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, tag, commit):
        return support.run(SCRIPT, tag, commit, cwd=self.repo)

    def test_newer_release_on_a_later_commit_passes(self):
        for tag in ("v1.0.1", "v1.1.0", "v1.1.0-rc.1", "v2.0.0"):
            with self.subTest(tag=tag):
                result = self.check(tag, self.commits[2])
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_same_or_older_version_is_refused(self):
        support.git(self.repo, "tag", "v1.2.0", self.commits[2])
        for tag in ("v1.2.0-rc.1", "v1.1.9", "v1.0.0"):
            with self.subTest(tag=tag):
                result = self.check(tag, self.commits[2])
                self.assertEqual(1, result.returncode, result.stdout)
                self.assertIn("is not newer than the latest release v1.2.0", result.stdout)

    def test_the_tag_being_released_does_not_count_as_earlier(self):
        support.git(self.repo, "tag", "v1.1.0", self.commits[2])   # pushed by hand, then this run started
        result = self.check("v1.1.0", self.commits[2])
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_release_on_an_older_commit_would_move_v1_back(self):
        result = self.check("v1.0.1", self.commits[0])
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("releasing it would move v1 back", result.stdout)

    def test_maintenance_release_of_an_older_major_after_a_new_major(self):
        """Projects still on @v1 can get a fix after v2.0.0: versions compare within the same major."""
        support.git(self.repo, "tag", "v2.0.0", self.commits[2])
        result = self.check("v1.0.1", self.commits[2])
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(1, self.check("v2.0.0-rc.1", self.commits[2]).returncode)

    def test_release_notes_skip_pre_releases(self):
        """v1.1.0's notes list everything since v1.0.0, not only what came after v1.1.0-rc.1."""
        support.git(self.repo, "commit", "-q", "--allow-empty", "-m", "feat: before the rc")
        support.git(self.repo, "tag", "v1.1.0-rc.1")
        support.git(self.repo, "commit", "-q", "--allow-empty", "-m", "fix: after the rc")
        result = support.run(support.SCRIPTS / "release-notes.sh", "v1.1.0", cwd=self.repo)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Changes since v1.0.0", result.stdout)
        self.assertIn("feat: before the rc", result.stdout)
        self.assertIn("fix: after the rc", result.stdout)

    def test_first_release_of_a_major_passes(self):
        result = self.check("v2.0.0", self.commits[0])   # no v2 tag yet, nothing to move back
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
