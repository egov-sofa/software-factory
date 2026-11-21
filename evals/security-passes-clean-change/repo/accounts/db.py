"""SQLite storage of the public profiles."""
import sqlite3

SCHEMA = "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL)"


def connect(path=":memory:"):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def add_user(conn, name, display_name):
    conn.execute("INSERT INTO users (name, display_name) VALUES (?, ?)", (name, display_name))
    conn.commit()
