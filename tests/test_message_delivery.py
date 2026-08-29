import unittest

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from core.tasks import (
    CHAT_EDITOR_INPUT_SELECTOR,
    CONVERSATION_SELECTED_SCRIPT,
    MESSAGE_COUNT_SCRIPT,
    MESSAGE_DELIVERED_SCRIPT,
    OUTGOING_MESSAGE_TEXT_SELECTOR,
    MessageDeliveryError,
    activate_conversation,
    ensure_all_targets_sent,
    send_message_verified,
)


class FakeChatInput:
    def __init__(self):
        self.typed = []
        self.pressed = []

    def type(self, value):
        self.typed.append(value)

    def press(self, key):
        self.pressed.append(key)


class FakePage:
    def __init__(self, delivery_error=None):
        self.delivery_error = delivery_error
        self.wait_arguments = None
        self.evaluate_arguments = []
        self.timeout_waits = []

    def evaluate(self, script, argument):
        self.evaluate_arguments.append(argument)
        return 2

    def wait_for_function(self, script, *, arg, timeout):
        self.wait_arguments = {"arg": arg, "timeout": timeout}
        if self.delivery_error:
            raise self.delivery_error

    def wait_for_timeout(self, timeout):
        self.timeout_waits.append(timeout)


class FakeConversationElement:
    def __init__(self):
        self.clicked = False
        self.handle = object()

    def click(self):
        self.clicked = True

    def element_handle(self):
        return self.handle


class MessageDeliveryTests(unittest.TestCase):
    def test_embedded_delivery_scripts_preserve_javascript_regex_escapes(self):
        self.assertIn(r"/\r\n/g", MESSAGE_COUNT_SCRIPT)
        self.assertIn(r"/\r\n/g", MESSAGE_DELIVERED_SCRIPT)

    def test_delivery_verifier_ignores_douyin_zero_width_editor_marker(self):
        self.assertIn(r"/[\u200B-\u200D\uFEFF]/g", MESSAGE_DELIVERED_SCRIPT)

    def test_delivery_verifier_counts_only_outgoing_message_bubbles(self):
        page = FakePage()
        chat_input = FakeChatInput()

        send_message_verified(page, chat_input, "hello")

        self.assertEqual(
            page.evaluate_arguments[0]["messageSelector"],
            OUTGOING_MESSAGE_TEXT_SELECTOR,
        )
        self.assertEqual(
            page.wait_arguments["arg"]["messageSelector"],
            OUTGOING_MESSAGE_TEXT_SELECTOR,
        )

    def test_conversation_must_be_selected_and_settled_before_sending(self):
        page = FakePage()
        element = FakeConversationElement()

        activate_conversation(page, element, timeout=4321)

        self.assertTrue(element.clicked)
        self.assertEqual(page.wait_arguments["arg"], element.handle)
        self.assertEqual(page.wait_arguments["timeout"], 4321)
        self.assertEqual(page.timeout_waits, [1000])
        self.assertIn("curConversation", CONVERSATION_SELECTED_SCRIPT)

    def test_send_requires_a_new_rendered_message_before_succeeding(self):
        page = FakePage()
        chat_input = FakeChatInput()

        send_message_verified(page, chat_input, "first\\nsecond", timeout=4321)

        self.assertEqual(chat_input.typed, ["first", "second"])
        self.assertEqual(chat_input.pressed, ["Shift+Enter", "Enter"])
        self.assertEqual(page.wait_arguments["arg"]["countBefore"], 2)
        self.assertEqual(
            page.wait_arguments["arg"]["editorSelector"],
            CHAT_EDITOR_INPUT_SELECTOR,
        )
        self.assertEqual(page.wait_arguments["timeout"], 4321)

    def test_unverified_send_fails_without_pressing_enter_twice(self):
        page = FakePage(delivery_error=PlaywrightTimeoutError("not rendered"))
        chat_input = FakeChatInput()

        with self.assertRaises(MessageDeliveryError):
            send_message_verified(page, chat_input, "hello", timeout=100)

        self.assertEqual(chat_input.pressed.count("Enter"), 1)

    def test_missing_targets_make_the_task_fail(self):
        with self.assertRaises(MessageDeliveryError):
            ensure_all_targets_sent(["friend-a", "friend-b"], {"friend-a"})

    def test_all_targets_sent_passes(self):
        ensure_all_targets_sent(["friend-a"], {"friend-a"})


if __name__ == "__main__":
    unittest.main()
