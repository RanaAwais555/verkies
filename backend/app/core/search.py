"""Helpers for simple text search."""


def contains_pattern(text: str) -> str:
    """A LIKE/ILIKE pattern matching `text` anywhere, with the wildcards in it escaped
    (backslash is Postgres' default LIKE escape character)."""
    escaped = text.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
