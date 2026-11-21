# Plan: Paginate the catalog listing

**Status:** Approved

## Goal
`list_items()` returns the whole catalog. The shop's pages need it one page at a time.

## Acceptance criteria
- [ ] `paginate(items, page, size)` in `catalog/paginate.py` returns the items of page `page` (1-based), `size` items
      per page, in catalog order.
- [ ] Every item is on exactly one page; the last page holds what is left and may be shorter.
- [ ] A page past the end returns an empty list.
- [ ] `page` or `size` below 1 raises `ValueError`.
- [ ] `page_count(total, size)` returns the number of pages (0 for an empty catalog).

## Files
- `catalog/paginate.py` (new)
- `tests/test_paginate.py` (new)

## Test plan
- A unit test for each criterion, with a catalog that does not divide evenly into pages.
