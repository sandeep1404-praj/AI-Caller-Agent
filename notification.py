"""Notification delivery for unavailable or non-responsive teachers."""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Iterable

from config import AppConfig
from models import NotificationMessage


class NotificationService:
    """Send email notifications or log them when email is unavailable."""

    def __init__(self, config: AppConfig, logger) -> None:
        self.config = config
        self.logger = logger

    def notify(self, message: NotificationMessage) -> None:
        """Notify the configured recipients for the message audience."""

        if not self.config.enable_notifications:
            self.logger.info("Notifications disabled: %s", message)
            return

        recipients = self._resolve_recipients(message.audience)
        if not recipients:
            self.logger.warning("No notification recipients configured for audience=%s", message.audience)
            return

        if self.config.smtp_host and self.config.smtp_sender:
            self._send_email(recipients, message)
        else:
            self.logger.info("Notification preview for %s: %s", recipients, message)

    def _resolve_recipients(self, audience: str) -> list[str]:
        audience_lower = audience.lower()
        recipients: list[str] = []
        if "hod" in audience_lower:
            recipients.extend(self.config.hod_recipients)
        if "coordinator" in audience_lower:
            recipients.extend(self.config.department_coordinator_recipients)
        if not recipients:
            recipients.extend(self.config.hod_recipients)
            recipients.extend(self.config.department_coordinator_recipients)
        return [recipient for recipient in recipients if recipient]

    def _send_email(self, recipients: Iterable[str], message: NotificationMessage) -> None:
        email = EmailMessage()
        email["Subject"] = f"Lecture Alert: {message.teacher_name} - {message.subject}"
        email["From"] = self.config.smtp_sender
        email["To"] = ", ".join(recipients)
        email.set_content(
            "\n".join(
                [
                    f"Teacher Name: {message.teacher_name}",
                    f"Teacher ID: {message.teacher_id}",
                    f"Department: {message.department}",
                    f"Subject: {message.subject}",
                    f"Lecture Time: {message.lecture_time}",
                    f"Reason: {message.reason}",
                    f"Retry Count: {message.retry_count}",
                    f"Phone Number: {message.phone_number}",
                ]
            )
        )

        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=30) as client:
            client.starttls()
            if self.config.smtp_username:
                client.login(self.config.smtp_username, self.config.smtp_password)
            client.send_message(email)
