from dataclasses import dataclass
from enum import Enum


class RunStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"


@dataclass(frozen=True)
class TargetSendResult:
    target_count: int
    verified_count: int

    def __post_init__(self):
        if self.target_count < 0:
            raise ValueError("target_count cannot be negative")
        if not 0 <= self.verified_count <= self.target_count:
            raise ValueError("verified_count must be within target_count")

    @property
    def failed_count(self):
        return self.target_count - self.verified_count


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    status: RunStatus
    target_count: int
    verified_count: int
    failed_count: int
    account_count: int
    completed_account_count: int
    duration_ms: int

    @classmethod
    def from_counts(
        cls,
        *,
        run_id,
        target_count,
        verified_count,
        account_count,
        completed_account_count,
        duration_ms,
    ):
        target_result = TargetSendResult(
            target_count=target_count,
            verified_count=verified_count,
        )
        if account_count < 0:
            raise ValueError("account_count cannot be negative")
        if not 0 <= completed_account_count <= account_count:
            raise ValueError("completed_account_count must be within account_count")
        if duration_ms < 0:
            raise ValueError("duration_ms cannot be negative")

        if target_result.verified_count == target_result.target_count and target_result.target_count:
            status = RunStatus.SUCCESS
        elif target_result.verified_count:
            status = RunStatus.PARTIAL_SUCCESS
        else:
            status = RunStatus.FAILED

        return cls(
            run_id=run_id,
            status=status,
            target_count=target_result.target_count,
            verified_count=target_result.verified_count,
            failed_count=target_result.failed_count,
            account_count=account_count,
            completed_account_count=completed_account_count,
            duration_ms=duration_ms,
        )
