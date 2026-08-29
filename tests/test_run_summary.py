import unittest

from core.results import RunStatus, RunSummary, TargetSendResult


class RunSummaryTests(unittest.TestCase):
    def test_all_verified_targets_are_success(self):
        summary = RunSummary.from_counts(
            run_id="run-1",
            target_count=3,
            verified_count=3,
            account_count=2,
            completed_account_count=2,
            duration_ms=1200,
        )

        self.assertEqual(summary.status, RunStatus.SUCCESS)
        self.assertEqual(summary.failed_count, 0)

    def test_some_verified_targets_are_partial_success(self):
        summary = RunSummary.from_counts(
            run_id="run-2",
            target_count=3,
            verified_count=1,
            account_count=2,
            completed_account_count=1,
            duration_ms=1200,
        )

        self.assertEqual(summary.status, RunStatus.PARTIAL_SUCCESS)
        self.assertEqual(summary.failed_count, 2)

    def test_zero_verified_targets_are_failed(self):
        summary = RunSummary.from_counts(
            run_id="run-3",
            target_count=3,
            verified_count=0,
            account_count=2,
            completed_account_count=0,
            duration_ms=1200,
        )

        self.assertEqual(summary.status, RunStatus.FAILED)
        self.assertEqual(summary.failed_count, 3)

    def test_invalid_counts_are_rejected(self):
        with self.assertRaises(ValueError):
            RunSummary.from_counts(
                run_id="run-4",
                target_count=1,
                verified_count=2,
                account_count=1,
                completed_account_count=1,
                duration_ms=0,
            )

    def test_target_result_tracks_failed_count_without_identifiers(self):
        result = TargetSendResult(target_count=4, verified_count=2)

        self.assertEqual(result.failed_count, 2)


if __name__ == "__main__":
    unittest.main()
