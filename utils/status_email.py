import os
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import parseaddr


GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 465
SMTP_TIMEOUT_SECONDS = 20
APP_PASSWORD_PATTERN = re.compile(r"^[A-Za-z0-9]{16}$")


class EmailConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class EmailConfig:
    sender: str
    recipient: str
    app_password: str


def _validated_email(value, field_name):
    normalized = value.strip()
    parsed_name, parsed_address = parseaddr(normalized)
    if (
        parsed_name
        or parsed_address != normalized
        or len(normalized) > 254
        or normalized.count("@") != 1
        or any(character in normalized for character in "\r\n")
    ):
        raise EmailConfigurationError(f"{field_name} must be one plain email address")
    return normalized


def load_email_config(environ=None):
    source = os.environ if environ is None else environ
    raw_sender = source.get("STATUS_EMAIL_FROM", "")
    raw_recipient = source.get("STATUS_EMAIL_TO", "")
    raw_password = source.get("STATUS_EMAIL_APP_PASSWORD", "")

    if not any((raw_sender, raw_recipient, raw_password)):
        return None
    if not all((raw_sender, raw_recipient, raw_password)):
        raise EmailConfigurationError("all status email settings are required")

    app_password = "".join(raw_password.split())
    if not APP_PASSWORD_PATTERN.fullmatch(app_password):
        raise EmailConfigurationError("status email app password must be 16 characters")

    return EmailConfig(
        sender=_validated_email(raw_sender, "STATUS_EMAIL_FROM"),
        recipient=_validated_email(raw_recipient, "STATUS_EMAIL_TO"),
        app_password=app_password,
    )


def build_status_message(summary, *, sender, recipient):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = (
        f"[DouYinSparkFlow] {summary.status.value} "
        f"— {summary.verified_count}/{summary.target_count} sent"
    )
    message.set_content(
        "\n".join(
            (
                f"Status: {summary.status.value}",
                f"Verified messages: {summary.verified_count}",
                f"Failed messages: {summary.failed_count}",
                f"Configured messages: {summary.target_count}",
                f"Completed accounts: {summary.completed_account_count}/{summary.account_count}",
                f"Duration: {summary.duration_ms / 1000:.2f} seconds",
                f"Cloud Run execution: {summary.run_id}",
                "Schedule: daily at 1:00 PM Asia/Singapore",
                "",
                "This report intentionally excludes account, recipient, message, and cookie details.",
            )
        )
    )
    return message


def send_status_email(
    summary,
    *,
    smtp_factory=smtplib.SMTP_SSL,
    tls_context_factory=ssl.create_default_context,
):
    config = load_email_config()
    if config is None:
        return False

    message = build_status_message(
        summary,
        sender=config.sender,
        recipient=config.recipient,
    )
    tls_context = tls_context_factory()
    with smtp_factory(
        GMAIL_SMTP_HOST,
        GMAIL_SMTP_PORT,
        timeout=SMTP_TIMEOUT_SECONDS,
        context=tls_context,
    ) as client:
        client.login(config.sender, config.app_password)
        client.send_message(message)
    return True
