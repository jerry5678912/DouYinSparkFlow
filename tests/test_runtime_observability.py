import unittest
from unittest.mock import patch

import core.tasks as tasks
from core.tasks import create_run_id


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
            with self.assertRaises(RuntimeError):
                tasks.runTasks()

        fields = log_error.call_args.kwargs["extra"]
        self.assertEqual(fields["event"], "run_failed")
        self.assertEqual(fields["run_id"], "run-123")
        self.assertEqual(fields["outcome"], "failure")
        self.assertEqual(fields["error_type"], "RuntimeError")


if __name__ == "__main__":
    unittest.main()
