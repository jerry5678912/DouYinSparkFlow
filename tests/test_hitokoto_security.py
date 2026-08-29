import unittest
from unittest.mock import Mock, patch

import utils.hitokoto as hitokoto


class HitokotoSecurityTests(unittest.TestCase):
    @patch("utils.hitokoto.get_config")
    @patch("utils.hitokoto.requests.get")
    def test_external_quote_is_bounded_and_redirects_are_rejected(
        self, requests_get, get_config
    ):
        get_config.return_value = {"hitokotoTypes": ["文学"]}
        response = Mock()
        response.json.return_value = {
            "hitokoto": "x" * 501,
            "from": "source",
            "from_who": "author",
        }
        response.status_code = 200
        requests_get.return_value = response

        result = hitokoto.request_hitokoto()

        self.assertEqual(result, "[error] 无法获取一言内容")
        requests_get.assert_called_once_with(
            "https://v1.hitokoto.cn/",
            params=[("c", "d")],
            timeout=10,
            allow_redirects=False,
        )


if __name__ == "__main__":
    unittest.main()
