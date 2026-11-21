import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import cli  # noqa: E402  (after the sys.path line above)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Path(self.tmp.name) / "tasks.json"

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        out = io.StringIO()
        self.assertEqual(0, cli.main(list(argv), store=self.store, out=out))
        return out.getvalue()

    def test_list_is_empty_at_first(self):
        self.assertEqual("", self.run_cli("list"))

    def test_added_tasks_are_listed_oldest_first(self):
        self.run_cli("add", "buy milk")
        self.run_cli("add", "call Ada")
        self.assertEqual("1. buy milk\n2. call Ada\n", self.run_cli("list"))
