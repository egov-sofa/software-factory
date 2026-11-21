"""Split the catalog into pages for the shop's listing."""


def page_count(total, size):
    """The number of pages for total items, size items per page."""
    if size < 1:
        raise ValueError("size must be at least 1")
    return (total + size - 1) // size


def paginate(items, page, size):
    """The items on page `page` (1-based), `size` per page; the last page may be shorter."""
    if page < 1 or size < 1:
        raise ValueError("page and size must be at least 1")
    start = (page - 1) * size
    return items[start:start + size]
