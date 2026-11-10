"""{{PROJECT_NAME}}."""


def greet(name: str) -> str:
    """Example function. Replace it with your own code."""
    trimmed = name.strip()
    if not trimmed:
        raise ValueError("name must not be empty")
    return f"Hello, {trimmed}!"
