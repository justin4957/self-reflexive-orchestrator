"""Multi-channel notification system for orchestrator events.

Supports Slack webhooks, email, and GitHub comments with rate limiting
and configurable event filtering.
"""

import json
import smtplib
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from collections import defaultdict
import requests

from ..core.logger import AuditLogger


@dataclass
class NotificationEvent:
    """Represents a notification event."""

    event_type: str
    title: str
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    severity: str = "info"  # info, warning, error, critical
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    link: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_type": self.event_type,
            "title": self.title,
            "message": self.message,
            "metadata": self.metadata,
            "severity": self.severity,
            "timestamp": self.timestamp.isoformat(),
            "link": self.link,
        }


@dataclass
class NotificationResult:
    """Result of notification delivery."""

    success: bool
    channel: str
    event_type: str
    error: Optional[str] = None
    rate_limited: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "channel": self.channel,
            "event_type": self.event_type,
            "error": self.error,
            "rate_limited": self.rate_limited,
            "timestamp": self.timestamp.isoformat(),
        }


class RateLimiter:
    """Simple in-memory rate limiter for notifications."""

    def __init__(
        self,
        max_per_hour: int = 10,
        max_per_event_per_hour: int = 3,
    ):
        """Initialize rate limiter.

        Args:
            max_per_hour: Maximum total notifications per hour
            max_per_event_per_hour: Maximum per event type per hour
        """
        self.max_per_hour = max_per_hour
        self.max_per_event_per_hour = max_per_event_per_hour
        self.timestamps: List[datetime] = []
        self.event_timestamps: Dict[str, List[datetime]] = defaultdict(list)

    def is_allowed(self, event_type: str) -> bool:
        """Check if notification is allowed.

        Args:
            event_type: Type of event

        Returns:
            True if allowed, False if rate limited
        """
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)

        # Clean old timestamps
        self.timestamps = [ts for ts in self.timestamps if ts > one_hour_ago]
        self.event_timestamps[event_type] = [
            ts for ts in self.event_timestamps[event_type] if ts > one_hour_ago
        ]

        # Check total rate limit
        if len(self.timestamps) >= self.max_per_hour:
            return False

        # Check per-event rate limit
        if len(self.event_timestamps[event_type]) >= self.max_per_event_per_hour:
            return False

        return True

    def record(self, event_type: str):
        """Record a notification send.

        Args:
            event_type: Type of event
        """
        now = datetime.now(timezone.utc)
        self.timestamps.append(now)
        self.event_timestamps[event_type].append(now)


class SlackNotifier:
    """Slack webhook notifier with rich formatting."""

    def __init__(self, webhook_url: str, logger: AuditLogger):
        """Initialize Slack notifier.

        Args:
            webhook_url: Slack webhook URL
            logger: Audit logger
        """
        self.webhook_url = webhook_url
        self.logger = logger

    def send(self, event: NotificationEvent) -> NotificationResult:
        """Send notification to Slack.

        Args:
            event: Notification event

        Returns:
            NotificationResult
        """
        try:
            # Build Slack message with blocks
            blocks = self._build_blocks(event)

            payload = {
                "text": f"{event.title}",
                "blocks": blocks,
            }

            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
            )

            if response.status_code == 200:
                self.logger.info(
                    "slack_notification_sent",
                    event_type=event.event_type,
                    severity=event.severity,
                )
                return NotificationResult(
                    success=True,
                    channel="slack",
                    event_type=event.event_type,
                )
            else:
                self.logger.error(
                    "slack_notification_failed",
                    event_type=event.event_type,
                    status_code=response.status_code,
                    response=response.text,
                )
                return NotificationResult(
                    success=False,
                    channel="slack",
                    event_type=event.event_type,
                    error=f"HTTP {response.status_code}: {response.text}",
                )

        except Exception as e:
            self.logger.error(
                "slack_notification_error",
                event_type=event.event_type,
                error=str(e),
                exc_info=True,
            )
            return NotificationResult(
                success=False,
                channel="slack",
                event_type=event.event_type,
                error=str(e),
            )

    def _build_blocks(self, event: NotificationEvent) -> List[Dict[str, Any]]:
        """Build Slack blocks for rich formatting.

        Args:
            event: Notification event

        Returns:
            List of Slack blocks
        """
        # Severity emoji
        severity_emoji = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🚨",
        }.get(event.severity, "ℹ️")

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{severity_emoji} {event.title}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": event.message,
                },
            },
        ]

        # Add metadata fields
        if event.metadata:
            fields = []
            for key, value in event.metadata.items():
                fields.append(
                    {
                        "type": "mrkdwn",
                        "text": f"*{key.replace('_', ' ').title()}:*\n{value}",
                    }
                )

            if fields:
                blocks.append(
                    {
                        "type": "section",
                        "fields": fields[:10],  # Slack limit
                    }
                )

        # Add link button if available
        if event.link:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View Details"},
                            "url": event.link,
                            "style": "primary",
                        }
                    ],
                }
            )

        # Add footer
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Event: `{event.event_type}` | Time: {event.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                    }
                ],
            }
        )

        return blocks


class EmailNotifier:
    """Email notifier with HTML formatting."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        from_email: str,
        to_email: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_tls: bool = True,
        logger: Optional[AuditLogger] = None,
    ):
        """Initialize email notifier.

        Args:
            smtp_host: SMTP server host
            smtp_port: SMTP server port
            from_email: From email address
            to_email: To email address
            username: SMTP username (if required)
            password: SMTP password (if required)
            use_tls: Use TLS encryption
            logger: Audit logger
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.from_email = from_email
        self.to_email = to_email
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.logger = logger

    def send(self, event: NotificationEvent) -> NotificationResult:
        """Send notification via email.

        Args:
            event: Notification event

        Returns:
            NotificationResult
        """
        try:
            # Build email
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[Orchestrator] {event.title}"
            msg["From"] = self.from_email
            msg["To"] = self.to_email

            # Plain text version
            text_content = self._build_text_content(event)
            text_part = MIMEText(text_content, "plain")

            # HTML version
            html_content = self._build_html_content(event)
            html_part = MIMEText(html_content, "html")

            msg.attach(text_part)
            msg.attach(html_part)

            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()

                if self.username and self.password:
                    server.login(self.username, self.password)

                server.send_message(msg)

            if self.logger:
                self.logger.info(
                    "email_notification_sent",
                    event_type=event.event_type,
                    to_email=self.to_email,
                )

            return NotificationResult(
                success=True,
                channel="email",
                event_type=event.event_type,
            )

        except Exception as e:
            if self.logger:
                self.logger.error(
                    "email_notification_error",
                    event_type=event.event_type,
                    error=str(e),
                    exc_info=True,
                )

            return NotificationResult(
                success=False,
                channel="email",
                event_type=event.event_type,
                error=str(e),
            )

    def _build_text_content(self, event: NotificationEvent) -> str:
        """Build plain text email content.

        Args:
            event: Notification event

        Returns:
            Plain text content
        """
        lines = [
            f"Orchestrator Notification",
            "=" * 50,
            "",
            f"Event: {event.event_type}",
            f"Severity: {event.severity.upper()}",
            f"Time: {event.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
            event.title,
            "-" * 50,
            "",
            event.message,
            "",
        ]

        if event.metadata:
            lines.append("Details:")
            lines.append("-" * 50)
            for key, value in event.metadata.items():
                lines.append(f"{key.replace('_', ' ').title()}: {value}")
            lines.append("")

        if event.link:
            lines.append(f"View Details: {event.link}")
            lines.append("")

        lines.append("-" * 50)
        lines.append("Self-Reflexive Coding Orchestrator")

        return "\n".join(lines)

    def _build_html_content(self, event: NotificationEvent) -> str:
        """Build HTML email content.

        Args:
            event: Notification event

        Returns:
            HTML content
        """
        severity_colors = {
            "info": "#3498db",
            "warning": "#f39c12",
            "error": "#e74c3c",
            "critical": "#c0392b",
        }
        color = severity_colors.get(event.severity, "#3498db")

        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: {color}; color: white; padding: 20px; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f9f9f9; padding: 20px; border-radius: 0 0 5px 5px; }}
                .metadata {{ background-color: white; padding: 15px; border-left: 4px solid {color}; margin: 15px 0; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
                .button {{ display: inline-block; padding: 10px 20px; background-color: {color}; color: white; text-decoration: none; border-radius: 5px; margin-top: 10px; }}
                table {{ width: 100%; border-collapse: collapse; }}
                td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
                td:first-child {{ font-weight: bold; width: 40%; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2 style="margin: 0;">🤖 {event.title}</h2>
                    <p style="margin: 5px 0 0 0; opacity: 0.9;">Event: {event.event_type}</p>
                </div>
                <div class="content">
                    <p>{event.message}</p>
        """

        if event.metadata:
            html += '<div class="metadata"><table>'
            for key, value in event.metadata.items():
                html += (
                    f"<tr><td>{key.replace('_', ' ').title()}</td><td>{value}</td></tr>"
                )
            html += "</table></div>"

        if event.link:
            html += f'<p><a href="{event.link}" class="button">View Details</a></p>'

        html += f"""
                    <p style="color: #666; font-size: 12px; margin-top: 20px;">
                        Severity: {event.severity.upper()} |
                        Time: {event.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}
                    </p>
                </div>
                <div class="footer">
                    <p>Self-Reflexive Coding Orchestrator</p>
                </div>
            </div>
        </body>
        </html>
        """

        return html


class GitHubCommentNotifier:
    """GitHub comment notifier for issue/PR updates."""

    def __init__(self, github_client, logger: AuditLogger):
        """Initialize GitHub comment notifier.

        Args:
            github_client: GitHub client
            logger: Audit logger
        """
        self.github_client = github_client
        self.logger = logger

    def send(self, event: NotificationEvent) -> NotificationResult:
        """Send notification as GitHub comment.

        Args:
            event: Notification event

        Returns:
            NotificationResult
        """
        try:
            # Extract issue/PR number from metadata
            issue_number = event.metadata.get("issue_number") or event.metadata.get(
                "pr_number"
            )

            if not issue_number:
                return NotificationResult(
                    success=False,
                    channel="github",
                    event_type=event.event_type,
                    error="No issue/PR number provided",
                )

            # Build comment
            comment = self._build_comment(event)

            # Post comment
            issue = self.github_client.repo.get_issue(int(issue_number))
            issue.create_comment(comment)

            self.logger.info(
                "github_comment_sent",
                event_type=event.event_type,
                issue_number=issue_number,
            )

            return NotificationResult(
                success=True,
                channel="github",
                event_type=event.event_type,
            )

        except Exception as e:
            self.logger.error(
                "github_comment_error",
                event_type=event.event_type,
                error=str(e),
                exc_info=True,
            )

            return NotificationResult(
                success=False,
                channel="github",
                event_type=event.event_type,
                error=str(e),
            )

    def _build_comment(self, event: NotificationEvent) -> str:
        """Build GitHub comment markdown.

        Args:
            event: Notification event

        Returns:
            Markdown comment
        """
        # Severity emoji
        severity_emoji = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🚨",
        }.get(event.severity, "ℹ️")

        lines = [
            f"## {severity_emoji} {event.title}",
            "",
            event.message,
            "",
        ]

        if event.metadata:
            lines.append("### Details")
            lines.append("")
            for key, value in event.metadata.items():
                if key not in ["issue_number", "pr_number"]:
                    lines.append(f"- **{key.replace('_', ' ').title()}**: {value}")
            lines.append("")

        if event.link:
            lines.append(f"[View Details]({event.link})")
            lines.append("")

        lines.append("---")
        lines.append(
            f"*Event: `{event.event_type}` | Time: {event.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}*"
        )
        lines.append("")
        lines.append("🤖 Self-Reflexive Coding Orchestrator")

        return "\n".join(lines)


class NotificationManager:
    """Manages multi-channel notifications with filtering and rate limiting."""

    def __init__(
        self,
        logger: AuditLogger,
        enabled_events: Optional[Set[str]] = None,
        slack_webhook: Optional[str] = None,
        email_config: Optional[Dict[str, Any]] = None,
        github_client: Optional[Any] = None,
        rate_limit_per_hour: int = 10,
        rate_limit_per_event_per_hour: int = 3,
    ):
        """Initialize notification manager.

        Args:
            logger: Audit logger
            enabled_events: Set of event types to notify on
            slack_webhook: Slack webhook URL
            email_config: Email configuration dict
            github_client: GitHub client
            rate_limit_per_hour: Max notifications per hour
            rate_limit_per_event_per_hour: Max per event type per hour
        """
        self.logger = logger
        self.enabled_events = enabled_events or set()
        self.rate_limiter = RateLimiter(
            max_per_hour=rate_limit_per_hour,
            max_per_event_per_hour=rate_limit_per_event_per_hour,
        )

        # Initialize channels
        self.channels: Dict[str, Any] = {}

        if slack_webhook:
            self.channels["slack"] = SlackNotifier(slack_webhook, logger)

        if email_config:
            self.channels["email"] = EmailNotifier(
                smtp_host=email_config.get("smtp_host", "localhost"),
                smtp_port=email_config.get("smtp_port", 587),
                from_email=email_config.get("from_email", ""),
                to_email=email_config.get("to_email", ""),
                username=email_config.get("username"),
                password=email_config.get("password"),
                use_tls=email_config.get("use_tls", True),
                logger=logger,
            )

        if github_client:
            self.channels["github"] = GitHubCommentNotifier(github_client, logger)

        self.logger.info(
            "notification_manager_initialized",
            channels=list(self.channels.keys()),
            enabled_events=list(self.enabled_events),
        )

    def notify(
        self,
        event: NotificationEvent,
        channels: Optional[List[str]] = None,
    ) -> List[NotificationResult]:
        """Send notification to specified channels.

        Args:
            event: Notification event
            channels: List of channels to send to (None = all)

        Returns:
            List of NotificationResults
        """
        results = []

        # Check if event is enabled
        if event.event_type not in self.enabled_events:
            self.logger.debug(
                "notification_skipped_disabled",
                event_type=event.event_type,
            )
            return results

        # Check rate limit
        if not self.rate_limiter.is_allowed(event.event_type):
            self.logger.warning(
                "notification_rate_limited",
                event_type=event.event_type,
            )
            results.append(
                NotificationResult(
                    success=False,
                    channel="all",
                    event_type=event.event_type,
                    rate_limited=True,
                    error="Rate limit exceeded",
                )
            )
            return results

        # Record notification
        self.rate_limiter.record(event.event_type)

        # Send to channels
        target_channels = channels or list(self.channels.keys())

        for channel_name in target_channels:
            if channel_name not in self.channels:
                self.logger.warning(
                    "notification_channel_not_configured",
                    channel=channel_name,
                )
                continue

            channel = self.channels[channel_name]
            result = channel.send(event)
            results.append(result)

        return results

    def notify_error(
        self,
        title: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
        link: Optional[str] = None,
    ) -> List[NotificationResult]:
        """Send error notification.

        Args:
            title: Error title
            message: Error message
            metadata: Additional metadata
            link: Link to details

        Returns:
            List of NotificationResults
        """
        event = NotificationEvent(
            event_type="error",
            title=title,
            message=message,
            metadata=metadata or {},
            severity="error",
            link=link,
        )
        return self.notify(event)

    def notify_merge(
        self,
        pr_number: int,
        pr_title: str,
        issue_number: Optional[int] = None,
        pr_url: Optional[str] = None,
    ) -> List[NotificationResult]:
        """Send PR merge notification.

        Args:
            pr_number: PR number
            pr_title: PR title
            issue_number: Related issue number
            pr_url: PR URL

        Returns:
            List of NotificationResults
        """
        metadata = {"pr_number": pr_number, "pr_title": pr_title}
        if issue_number:
            metadata["issue"] = f"Closes #{issue_number}"

        event = NotificationEvent(
            event_type="merge",
            title=f"PR Merged: #{pr_number}",
            message=f"Pull request **{pr_title}** has been merged successfully.",
            metadata=metadata,
            severity="info",
            link=pr_url,
        )
        return self.notify(event)

    def notify_approval_required(
        self,
        title: str,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None,
        link: Optional[str] = None,
    ) -> List[NotificationResult]:
        """Send human approval required notification.

        Args:
            title: Approval request title
            reason: Reason for approval
            metadata: Additional metadata
            link: Link to approval

        Returns:
            List of NotificationResults
        """
        event = NotificationEvent(
            event_type="human_approval_required",
            title=title,
            message=f"**Approval Required**: {reason}",
            metadata=metadata or {},
            severity="warning",
            link=link,
        )
        return self.notify(event)
