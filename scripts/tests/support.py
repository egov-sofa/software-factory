"""Shared helpers for the tests that run the factory's shell scripts (install.sh, uninstall.sh, new-project.sh).

The scripts run under the real bash, with an isolated environment: an empty global git config, no system git config
and a fixed git identity, so the developer's own hooks, signing or hooksPath cannot change the results.
"""
import atexit
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[2]
SCRIPTS = FACTORY / "scripts"


def find_bash():
    """The bash to run the scripts with, or None. ["bash", ...] is not used directly: on Windows, the system searches
    System32 before PATH and would pick WSL's bash, which cannot read Windows paths the same way."""
    bash = os.environ.get("FACTORY_TEST_BASH") or shutil.which("bash")
    if not bash:
        return None
    bash = str(Path(bash).resolve())
    if os.name == "nt" and Path(bash).parent.name.lower() == "system32":
        return None   # WSL, not Git Bash
    return bash


BASH = find_bash()
needs_bash = unittest.skipUnless(BASH, "bash not found (on Windows, Git Bash must be on PATH or set FACTORY_TEST_BASH)")

_GIT_CONFIG = tempfile.NamedTemporaryFile(prefix="factory-test-gitconfig-", delete=False)
_GIT_CONFIG.close()
_GH_CONFIG = tempfile.TemporaryDirectory(prefix="factory-test-gh-")
atexit.register(lambda: Path(_GIT_CONFIG.name).unlink(missing_ok=True))
atexit.register(_GH_CONFIG.cleanup)


def environment(**extra):
    # An empty GitHub CLI config and no token: gh is logged out, so a test never reaches GitHub or the real account.
    env = {**os.environ, "GIT_CONFIG_GLOBAL": _GIT_CONFIG.name, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
           "GH_CONFIG_DIR": _GH_CONFIG.name, "GH_PROMPT_DISABLED": "1"}
    for name in ("FACTORY_WORKSPACE", "CLAUDE_CONFIG_DIR", "GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN",
                 "GITHUB_ENTERPRISE_TOKEN"):
        env.pop(name, None)
    env.update(extra)
    return env


def posix(path):
    """A path bash understands on every platform (C:/... works in Git Bash)."""
    return Path(path).as_posix()


def run(script, *args, env=None, cwd=None):
    """Run a shell script with bash; arguments that are paths should go through posix() first."""
    return subprocess.run([BASH, posix(script), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=environment(**(env or {})), cwd=cwd, check=False)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=environment(), check=True).stdout
