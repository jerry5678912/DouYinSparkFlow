import unittest

import core.tasks as tasks


class FakePage:
    def __init__(self):
        self.goto_calls = []
        self.selector_waits = []

    def goto(self, **kwargs):
        self.goto_calls.append(kwargs)

    def wait_for_selector(self, selector, timeout):
        self.selector_waits.append((selector, timeout))


class ChatStartupTests(unittest.TestCase):
    def test_chat_startup_does_not_wait_for_spa_full_load_event(self):
        page = FakePage()

        tasks.open_chat_page(page)

        self.assertEqual(
            page.goto_calls,
            [{"url": "https://www.douyin.com/chat", "wait_until": "domcontentloaded"}],
        )
        self.assertEqual(
            page.selector_waits,
            [(tasks.CONVERSATION_LIST_SELECTOR, tasks.config["browserTimeout"])],
        )


if __name__ == "__main__":
    unittest.main()
