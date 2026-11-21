"""The items of the catalog, in the order the shop shows them."""

ITEMS = ["apple", "bread", "cheese", "dates", "eggs", "flour", "grapes"]


def list_items():
    """A copy of every item, so a caller cannot change the catalog."""
    return list(ITEMS)
