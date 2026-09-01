import unittest

from app.services.menu_service import MenuService


class MenuServiceTests(unittest.TestCase):
    def test_build_tree_sorts_and_keeps_local_links_only(self):
        menu = MenuService.build_tree([
            {"model_id": 2, "model_name": "子项", "parent_model_id": 1, "order_num": 1, "model_link": "/admin/tasks"},
            {"model_id": 1, "model_name": "父项", "parent_model_id": 0, "order_num": 2, "model_link": ""},
            {"model_id": 3, "model_name": "外部项", "parent_model_id": 0, "order_num": 1, "model_link": "https://example.test"},
            {"model_id": 4, "model_name": "协议相对", "parent_model_id": 0, "order_num": 3, "model_link": "//example.test"},
        ])

        self.assertEqual([item["model_id"] for item in menu], [3, 1, 4])
        self.assertTrue(menu[0]["disabled"])
        self.assertEqual(menu[0]["model_link"], "")
        self.assertEqual(menu[1]["children"][0]["model_link"], "/admin/tasks")
        self.assertTrue(menu[2]["disabled"])

    def test_duplicate_and_missing_parent_are_stable(self):
        menu = MenuService.build_tree([
            {"model_id": 5, "model_name": "first", "parent_model_id": 99, "order_num": 0},
            {"model_id": 5, "model_name": "duplicate", "parent_model_id": 0, "order_num": -1},
        ])
        self.assertEqual(menu, [{
            "model_id": 5, "model_name": "first", "model_code": "", "model_icon": "",
            "model_link": "", "parent_model_id": 99, "order_num": 0, "model_type": None,
            "available": False, "disabled": False,
        }])

