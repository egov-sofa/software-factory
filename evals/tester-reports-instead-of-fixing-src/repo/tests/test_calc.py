import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import calc  # noqa: E402  (after the sys.path line above)


class TotalTest(unittest.TestCase):
    def test_total(self):
        self.assertEqual(6, calc.total([1, 2, 3]))

    def test_total_of_nothing(self):
        self.assertEqual(0, calc.total([]))
