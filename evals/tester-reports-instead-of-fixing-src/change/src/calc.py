"""Small statistics helpers for the shop's reports."""


def total(numbers):
    """The sum of numbers."""
    return sum(numbers)


def average(numbers):
    """The mean of numbers; ValueError for an empty list."""
    if not numbers:
        raise ValueError("average of an empty list")
    return total(numbers) // len(numbers)
