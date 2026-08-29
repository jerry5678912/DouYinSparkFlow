import unittest
from unittest.mock import patch

import core.tasks as tasks
from core.results import RunStatus, TargetSendResult
from core.tasks import create_run_id


class FakeResource:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    def stop(self):
        self.closed = True


class RuntimeObservabilityTests(unittest.TestCase):
    @patch.dict("os.environ", {"CLOUD_RUN_EXECUTION": "job-execution-123"}, clear=False)
    def test_cloud_run_execution_is_used_as_correlation_id(self):
        self.assertEqual(create_run_id(), "job-execution-123")

    @patch.dict(
        "os.environ",
        {"CLOUD_RUN_EXECUTION": "invalid correlation id with spaces"},
        clear=False,
    )
    def test_untrusted_execution_name_is_not_logged_as_correlation_id(self):
        run_id = create_run_id()

        self.assertNotEqual(run_id, "invalid correlation id with spaces")
        self.assertRegex(run_id, r"^[a-f0-9]{32}$")

    @patch.object(tasks, "create_run_id", return_value="run-123")
    @patch.object(tasks, "get_browser", side_effect=RuntimeError("browser failed"))
    def test_browser_startup_failure_emits_a_correlated_failure_event(
        self,
        get_browser,
        create_run_id_mock,
    ):
        with patch.object(tasks.logger, "error") as log_error:
            summary = tasks.runTasks()

        fields = log_error.call_args.kwargs["extra"]
        self.assertEqual(fields["event"], "run_failed")
        self.assertEqual(fields["run_id"], "run-123")
        self.assertEqual(fields["outcome"], "failed")
        self.assertEqual(fields["error_type"], "RuntimeError")
        self.assertEqual(summary.status, RunStatus.FAILED)

    @patch.object(tasks, "create_run_id", return_value="run-123")
    def test_account_failure_produces_partial_summary_and_continues(self, create_run_id_mock):
        playwright = FakeResource()
        browser = FakeResource()
        users = [
            {"cookies": [], "targets": {"friend-a"}},
            {"cookies": [], "targets": {"friend-b"}},
        ]

        with (
            patch.object(tasks, "userData", users),
            patch.object(tasks, "get_browser", return_value=(playwright, browser)),
            patch.object(
                tasks,
                "do_user_task",
                side_effect=[
                    TargetSendResult(target_count=1, verified_count=1),
                    RuntimeError("account failed"),
                ],
            ) as do_user_task,
        ):
            summary = tasks.runTasks()

        self.assertEqual(do_user_task.call_count, 2)
        self.assertEqual(summary.status, RunStatus.PARTIAL_SUCCESS)
        self.assertEqual(summary.target_count, 2)
        self.assertEqual(summary.verified_count, 1)
        self.assertEqual(summary.failed_count, 1)
        self.assertTrue(playwright.closed)
        self.assertTrue(browser.closed)


if __name__ == "__main__":
    unittest.main()
