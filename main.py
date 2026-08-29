import os
import sys

if os.path.exists(".env"):
    from dotenv import load_dotenv

    load_dotenv(".env")

from core.results import RunStatus
from core.tasks import runTasks
from core.tasks import logger
from utils.status_email import send_status_email


def main():
    summary = runTasks()
    try:
        email_sent = send_status_email(summary)
    except Exception as error:
        logger.error(
            "Daily status email could not be sent",
            extra={
                "event": "status_email_failed",
                "run_id": summary.run_id,
                "outcome": summary.status.value.lower(),
                "error_type": type(error).__name__,
            },
        )
        return 2

    logger.info(
        "Daily status email processed",
        extra={
            "event": "status_email_sent" if email_sent else "status_email_disabled",
            "run_id": summary.run_id,
            "outcome": summary.status.value.lower(),
        },
    )
    return 0 if summary.status is RunStatus.SUCCESS else 1


if __name__ == "__main__":
    sys.exit(main())
