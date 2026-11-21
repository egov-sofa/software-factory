import unittest

from catalog.items import list_items
from catalog.paginate import page_count, paginate


class PaginateTest(unittest.TestCase):
    def setUp(self):
        self.items = list_items()   # 7 items

    def test_first_page_starts_with_the_first_item(self):
        self.assertEqual("apple", paginate(self.items, 1, 3)[0])

    def test_second_page_starts_after_the_first(self):
        self.assertEqual("dates", paginate(self.items, 2, 3)[0])

    def test_page_past_the_end_is_empty(self):
        self.assertEqual([], paginate(self.items, 4, 3))

    def test_page_and_size_below_one_are_refused(self):
        with self.assertRaises(ValueError):
            paginate(self.items, 0, 3)
        with self.assertRaises(ValueError):
            paginate(self.items, 1, 0)

    def test_page_count(self):
        self.assertEqual(3, page_count(7, 3))
        self.assertEqual(0, page_count(0, 3))
