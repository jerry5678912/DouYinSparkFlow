import unittest
from unittest.mock import patch

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

import core.tasks as tasks

from core.tasks import (
    CHAT_EDITOR_INPUT_SELECTOR,
    CONVERSATION_SELECTED_SCRIPT,
    MESSAGE_COUNT_SCRIPT,
    MESSAGE_DELIVERED_SCRIPT,
    OUTGOING_MESSAGE_TEXT_SELECTOR,
    POST_SEND_SETTLE_MS,
    TRUST_LOGIN_CANCEL_SELECTOR,
    MessageDeliveryError,
    activate_conversation,
    dismiss_trust_login_dialog,
    ensure_all_targets_sent,
    send_message_verified,
    target_identity_data_ready,
    wait_for_target_identity_data,
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
    def __init__(self, delivery_error=None, delivery_errors=None):
        self.delivery_error = delivery_error
        self.delivery_errors = list(delivery_errors or [])
        self.wait_arguments = None
        self.wait_calls = []
        self.evaluate_arguments = []
        self.timeout_waits = []
        self.send_button = FakeSendButton()
        self.waited_selectors = []

    def evaluate(self, script, argument):
        self.evaluate_arguments.append(argument)
        return 2

    def wait_for_function(self, script, *, arg, timeout):
        self.wait_arguments = {"arg": arg, "timeout": timeout}
        self.wait_calls.append(self.wait_arguments)
        if self.delivery_errors:
            error = self.delivery_errors.pop(0)
            if error is not None:
                raise error
        elif self.delivery_error is not None:
            raise self.delivery_error

    def wait_for_timeout(self, timeout):
        self.timeout_waits.append(timeout)

    def wait_for_selector(self, selector, timeout):
        self.waited_selectors.append((selector, timeout))

    def locator(self, selector):
        if selector == CHAT_EDITOR_INPUT_SELECTOR:
            return FakeChatInput()
        raise AssertionError(f"unexpected selector: {selector}")


class FakeSendButton:
    def __init__(self):
        self.click_count = 0

    def click(self):
        self.click_count += 1


class FakeTrustLoginCancel:
    def __init__(self, error=None):
        self.error = error
        self.click_timeouts = []

    def click(self, timeout):
        self.click_timeouts.append(timeout)
        if self.error:
            raise self.error


class FakeTrustLoginPage:
    def __init__(self, error=None):
        self.cancel = FakeTrustLoginCancel(error=error)
        self.located = []

    def locator(self, selector):
        self.located.append(selector)
        return self.cancel


class FakeConversationElement:
    def __init__(self):
        self.clicked = False
        self.handle = object()

    def click(self):
        self.clicked = True

    def element_handle(self):
        return self.handle


class FakeIdentityPage:
    def __init__(self, on_wait=None):
        self.on_wait = on_wait
        self.timeout_waits = []

    def wait_for_timeout(self, timeout):
        self.timeout_waits.append(timeout)
        if self.on_wait:
            self.on_wait(len(self.timeout_waits))


class MessageDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.saved_user_id_dict = dict(tasks.userIDDict)
        tasks.userIDDict.clear()

    def tearDown(self):
        tasks.userIDDict.clear()
        tasks.userIDDict.update(self.saved_user_id_dict)

    def test_embedded_delivery_scripts_preserve_javascript_regex_escapes(self):
        self.assertIn(r"/\r\n?/g", MESSAGE_COUNT_SCRIPT)
        self.assertIn(r"/\r\n?/g", MESSAGE_DELIVERED_SCRIPT)

    def test_delivery_verifier_ignores_douyin_zero_width_editor_marker(self):
        self.assertIn(r"/[\u200B-\u200D\uFEFF]/g", MESSAGE_DELIVERED_SCRIPT)

    def test_delivery_verifier_normalizes_outgoing_bubble_text(self):
        self.assertIn(r"/[\u200B-\u200D\uFEFF]/g", MESSAGE_COUNT_SCRIPT)
        self.assertIn(r"/\u00A0/g", MESSAGE_COUNT_SCRIPT)
        self.assertIn(r"/\u00A0/g", MESSAGE_DELIVERED_SCRIPT)

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
        self.assertEqual(page.send_button.click_count, 0)
        self.assertEqual(page.waited_selectors, [])
        self.assertEqual(page.wait_arguments["arg"]["countBefore"], 2)
        self.assertEqual(
            page.wait_arguments["arg"]["editorSelector"],
            CHAT_EDITOR_INPUT_SELECTOR,
        )
        self.assertEqual(page.wait_arguments["timeout"], 4321)
        self.assertEqual(page.timeout_waits, [POST_SEND_SETTLE_MS])

    def test_delayed_delivery_is_rechecked_without_pressing_enter_twice(self):
        page = FakePage(
            delivery_errors=[PlaywrightTimeoutError("late render"), None]
        )
        chat_input = FakeChatInput()

        send_message_verified(page, chat_input, "hello", timeout=100)

        self.assertEqual(chat_input.pressed, ["Enter"])
        self.assertEqual(len(page.wait_calls), 2)
        self.assertEqual(page.timeout_waits, [POST_SEND_SETTLE_MS])

    def test_unverified_send_fails_without_pressing_enter_twice(self):
        page = FakePage(delivery_error=PlaywrightTimeoutError("not rendered"))
        chat_input = FakeChatInput()

        with self.assertRaises(MessageDeliveryError):
            send_message_verified(page, chat_input, "hello", timeout=100)

        self.assertEqual(chat_input.pressed, ["Enter"])
        self.assertEqual(page.send_button.click_count, 0)
        self.assertEqual(page.timeout_waits, [])

    @patch.object(tasks, "prepare_chat_page")
    @patch.object(tasks, "send_message_verified")
    @patch.object(tasks, "build_message", return_value="hello")
    def test_target_search_retries_only_targets_not_already_sent(
        self,
        build_message,
        send_message,
        prepare_chat_page,
    ):
        page = FakePage()
        scans = []

        def scan_targets(_page, _account_label, targets):
            scans.append(set(targets))
            return iter(["friend-a"] if len(scans) == 1 else ["friend-b"])

        with patch.object(tasks, "scroll_and_select_user", side_effect=scan_targets):
            sent = tasks.send_targets_with_recovery(
                page,
                "account-1",
                {"friend-a", "friend-b"},
                max_search_attempts=2,
            )

        self.assertEqual(scans, [{"friend-a", "friend-b"}, {"friend-b"}])
        self.assertEqual(sent, {"friend-a", "friend-b"})
        self.assertEqual(send_message.call_count, 2)
        prepare_chat_page.assert_called_once_with(
            page,
            "account-1",
            {"friend-b"},
        )

    def test_trust_login_prompt_is_cancelled_when_present(self):
        page = FakeTrustLoginPage()

        self.assertTrue(dismiss_trust_login_dialog(page, timeout=2345))

        self.assertEqual(page.located, [TRUST_LOGIN_CANCEL_SELECTOR])
        self.assertEqual(page.cancel.click_timeouts, [2345])

    def test_missing_trust_login_prompt_is_safe(self):
        page = FakeTrustLoginPage(error=PlaywrightTimeoutError("not visible"))

        self.assertFalse(dismiss_trust_login_dialog(page, timeout=100))

    def test_missing_targets_make_the_task_fail(self):
        with self.assertRaises(MessageDeliveryError):
            ensure_all_targets_sent(["friend-a", "friend-b"], {"friend-a"})

    def test_all_targets_sent_passes(self):
        ensure_all_targets_sent(["friend-a"], {"friend-a"})

    def test_target_identity_readiness_matches_any_douyin_identifier(self):
        tasks.userIDDict["Friend"] = [
            "short-id",
            "2000C616",
            "sec-id",
            "Friend",
            "Friend",
        ]

        self.assertTrue(target_identity_data_ready({"2000C616"}))
        self.assertFalse(target_identity_data_ready({"unrelated-id"}))

    def test_target_identity_wait_stops_as_soon_as_response_data_arrives(self):
        def populate_after_second_poll(poll_count):
            if poll_count == 2:
                tasks.userIDDict["Friend"] = [
                    "short-id",
                    "2000C616",
                    "sec-id",
                    "Friend",
                    "Friend",
                ]

        page = FakeIdentityPage(on_wait=populate_after_second_poll)

        self.assertTrue(
            wait_for_target_identity_data(
                page,
                {"2000C616"},
                timeout=500,
                poll_interval=100,
            )
        )
        self.assertEqual(page.timeout_waits, [100, 100])

    def test_target_identity_wait_uses_exact_timeout(self):
        page = FakeIdentityPage()

        self.assertFalse(
            wait_for_target_identity_data(
                page,
                {"missing-id"},
                timeout=250,
                poll_interval=100,
            )
        )
        self.assertEqual(page.timeout_waits, [100, 100, 50])


if __name__ == "__main__":
    unittest.main()
