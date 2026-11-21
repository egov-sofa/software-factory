import unittest

from catalog.items import list_items
from catalog.paginate import page_count, paginate


class PaginateTest(unittest.TestCase):
    def setUp(self):
        self.items = list_items()   # 7 items: 3 pages of 3, the last one shorter

    def test_full_pages(self):
        self.assertEqual(["apple", "bread", "cheese"], paginate(self.items, 1, 3))
        self.assertEqual(["dates", "eggs", "flour"], paginate(self.items, 2, 3))

    def test_last_page_holds_what_is_left(self):
        self.assertEqual(["grapes"], paginate(self.items, 3, 3))

    def test_every_item_is_on_exactly_one_page(self):
        for size in (1, 2, 3, 7, 10):
            with self.subTest(size=size):
                pages = [paginate(self.items, page, size) for page in range(1, page_count(len(self.items), size) + 1)]
                self.assertEqual(self.items, [item for page in pages for item in page])

    def test_page_past_the_end_is_empty(self):
        self.assertEqual([], paginate(self.items, 4, 3))
        self.assertEqual([], paginate([], 1, 3))

    def test_page_and_size_below_one_are_refused(self):
        for page, size in ((0, 3), (-1, 3), (1, 0), (1, -2)):
            with self.subTest(page=page, size=size), self.assertRaises(ValueError):
                paginate(self.items, page, size)

    def test_page_count(self):
        self.assertEqual(3, page_count(7, 3))
        self.assertEqual(2, page_count(6, 3))
        self.assertEqual(0, page_count(0, 3))
        with self.assertRaises(ValueError):
            page_count(7, 0)
