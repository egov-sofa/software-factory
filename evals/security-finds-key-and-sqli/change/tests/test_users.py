import unittest

from accounts import db
from accounts.users import find_user


class FindUserTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect()
        db.add_user(self.conn, "ada", "Ada L.")

    def test_existing_user(self):
        self.assertEqual({"name": "ada", "display_name": "Ada L."}, find_user(self.conn, "ada"))

    def test_unknown_user(self):
        self.assertIsNone(find_user(self.conn, "grace"))
