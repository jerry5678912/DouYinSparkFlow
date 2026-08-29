import importlib
import sys
import unittest
from unittest.mock import patch

import core.tasks as tasks
from core.results import RunSummary


class MainStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.object(tasks, "runTasks"):
            sys.modules.pop("main", None)
            cls.main_module = importlib.import_module("main")

    def test_success_email_is_sent_before_zero_exit_code(self):
        summary = RunSummary.from_counts(
            run_id="run-success",
            target_count=1,
            verified_count=1,
            account_count=1,
            completed_account_count=1,
            duration_ms=100,
        )

        with (
            patch.object(self.main_module, "runTasks", return_value=summary),
            patch.object(self.main_module, "send_status_email", return_value=True) as send_email,
        ):
            exit_code = self.main_module.main()

        send_email.assert_called_once_with(summary)
        self.assertEqual(exit_code, 0)

    def test_partial_success_email_is_sent_before_nonzero_exit_code(self):
        summary = RunSummary.from_counts(
            run_id="run-partial",
            target_count=2,
            verified_count=1,
            account_count=1,
            completed_account_count=0,
            duration_ms=100,
        )

        with (
            patch.object(self.main_module, "runTasks", return_value=summary),
            patch.object(self.main_module, "send_status_email", return_value=True) as send_email,
        ):
            exit_code = self.main_module.main()

        send_email.assert_called_once_with(summary)
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
