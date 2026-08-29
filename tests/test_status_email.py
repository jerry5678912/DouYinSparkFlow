import os
import unittest
from unittest.mock import patch

from core.results import RunSummary
from utils.status_email import (
    EmailConfigurationError,
    build_status_message,
    load_email_config,
    send_status_email,
)


class FakeSmtpClient:
    def __init__(self):
        self.login_args = None
        self.sent_message = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.sent_message = message


class StatusEmailTests(unittest.TestCase):
    def setUp(self):
        self.summary = RunSummary.from_counts(
            run_id="job-execution-123",
            target_count=3,
            verified_count=1,
            account_count=2,
            completed_account_count=1,
            duration_ms=12500,
        )

    @patch.dict(os.environ, {}, clear=True)
    def test_email_is_disabled_when_no_email_settings_exist(self):
        self.assertIsNone(load_email_config())

    @patch.dict(
        os.environ,
        {"STATUS_EMAIL_FROM": "sender@gmail.com"},
        clear=True,
    )
    def test_partial_email_configuration_fails_closed(self):
        with self.assertRaises(EmailConfigurationError):
            load_email_config()

    def test_partial_success_email_contains_counts_but_no_recipient_details(self):
        message = build_status_message(
            self.summary,
            sender="sender@gmail.com",
            recipient="owner@gmail.com",
        )

        self.assertIn("PARTIAL_SUCCESS", message["Subject"])
        self.assertIn("Verified messages: 1", message.get_content())
        self.assertIn("Failed messages: 2", message.get_content())
        self.assertNotIn("friend", message.get_content().lower())

    @patch.dict(
        os.environ,
        {
            "STATUS_EMAIL_FROM": "sender@gmail.com",
            "STATUS_EMAIL_TO": "owner@gmail.com",
            "STATUS_EMAIL_APP_PASSWORD": "abcd efgh ijkl mnop",
        },
        clear=True,
    )
    def test_smtp_uses_fixed_gmail_tls_endpoint_and_normalized_app_password(self):
        smtp_client = FakeSmtpClient()
        calls = []

        def smtp_factory(host, port, *, timeout, context):
            calls.append((host, port, timeout, context))
            return smtp_client

        tls_context = object()
        self.assertTrue(
            send_status_email(
                self.summary,
                smtp_factory=smtp_factory,
                tls_context_factory=lambda: tls_context,
            )
        )

        self.assertEqual(calls[0][0:3], ("smtp.gmail.com", 465, 20))
        self.assertIs(calls[0][3], tls_context)
        self.assertEqual(
            smtp_client.login_args,
            ("sender@gmail.com", "abcdefghijklmnop"),
        )
        self.assertEqual(smtp_client.sent_message["To"], "owner@gmail.com")


if __name__ == "__main__":
    unittest.main()
