import unittest

from catalog.items import list_items


class ListItemsTest(unittest.TestCase):
    def test_every_item_in_order(self):
        self.assertEqual(["apple", "bread", "cheese", "dates", "eggs", "flour", "grapes"], list_items())

    def test_a_copy(self):
        list_items().clear()
        self.assertEqual(7, len(list_items()))
