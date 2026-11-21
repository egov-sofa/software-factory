import sqlite3
import unittest

from accounts import db


class DbTest(unittest.TestCase):
    def test_add_user(self):
        conn = db.connect()
        db.add_user(conn, "ada", "Ada L.")
        self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def test_names_are_unique(self):
        conn = db.connect()
        db.add_user(conn, "ada", "Ada L.")
        with self.assertRaises(sqlite3.IntegrityError):
            db.add_user(conn, "ada", "Another Ada")
