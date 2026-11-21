"""Public profiles by name."""


def find_user(conn, name):
    """The public profile of the user called name, or None."""
    row = conn.execute(f"SELECT name, display_name FROM users WHERE name = '{name}'").fetchone()
    return {"name": row["name"], "display_name": row["display_name"]} if row else None
