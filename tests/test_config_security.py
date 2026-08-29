import os
import unittest
from unittest.mock import patch

import utils.config as config_module


class ConfigSecurityTests(unittest.TestCase):
    def tearDown(self):
        config_module.config = None
        config_module.userData = None

    def test_numeric_configuration_is_bounded(self):
        with patch.dict(os.environ, {"TASK_RETRY_TIMES": "1000"}, clear=True):
            with self.assertRaisesRegex(ValueError, "TASK_RETRY_TIMES"):
                config_module.get_config()

    def test_hitokoto_types_must_be_a_list_of_supported_values(self):
        with patch.dict(os.environ, {"HITOKOTO_TYPES": '{"bad": true}'}, clear=True):
            with self.assertRaisesRegex(ValueError, "HITOKOTO_TYPES"):
                config_module.get_config()

    def test_tasks_must_be_a_bounded_json_list(self):
        with patch.dict(os.environ, {"TASKS": '{"username": "not-a-list"}'}, clear=True):
            with self.assertRaisesRegex(ValueError, "TASKS"):
                config_module.get_userData()

    def test_cookie_payload_must_be_a_json_list(self):
        task_json = '[{"username":"test","unique_id":"one","targets":["friend"]}]'
        with patch.dict(
            os.environ,
            {"TASKS": task_json, "COOKIES_ONE": '{"sessionid":"bad-shape"}'},
            clear=True,
        ):
            self.assertEqual(config_module.get_userData(), [])


if __name__ == "__main__":
    unittest.main()
