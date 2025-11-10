"""Unit tests for notification system."""

import unittest
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime, timezone, timedelta

from src.integrations.notifications import (
    NotificationManager,
    NotificationEvent,
    NotificationResult,
    RateLimiter,
    SlackNotifier,
    EmailNotifier,
    GitHubCommentNotifier,
)
from src.core.logger import AuditLogger


class TestRateLimiter(unittest.TestCase):
    """Test cases for RateLimiter."""

    def test_initialization(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter(max_per_hour=10, max_per_event_per_hour=3)
        self.assertEqual(limiter.max_per_hour, 10)
        self.assertEqual(limiter.max_per_event_per_hour, 3)

    def test_allows_initial_requests(self):
        """Test that initial requests are allowed."""
        limiter = RateLimiter(max_per_hour=10, max_per_event_per_hour=3)
        self.assertTrue(limiter.is_allowed("test_event"))

    def test_blocks_after_per_event_limit(self):
        """Test blocking after per-event limit."""
        limiter = RateLimiter(max_per_hour=10, max_per_event_per_hour=3)

        # Record 3 events
        for _ in range(3):
            self.assertTrue(limiter.is_allowed("test_event"))
            limiter.record("test_event")

        # 4th should be blocked
        self.assertFalse(limiter.is_allowed("test_event"))

    def test_blocks_after_total_limit(self):
        """Test blocking after total limit."""
        limiter = RateLimiter(max_per_hour=5, max_per_event_per_hour=3)

        # Record 5 different events
        for i in range(5):
            self.assertTrue(limiter.is_allowed(f"event_{i}"))
            limiter.record(f"event_{i}")

        # 6th event should be blocked
        self.assertFalse(limiter.is_allowed("event_6"))

    def test_different_events_tracked_separately(self):
        """Test that different events are tracked separately."""
        limiter = RateLimiter(max_per_hour=10, max_per_event_per_hour=2)

        # Record 2 of event_a
        limiter.record("event_a")
        limiter.record("event_a")

        # event_a should be blocked
        self.assertFalse(limiter.is_allowed("event_a"))

        # event_b should still be allowed
        self.assertTrue(limiter.is_allowed("event_b"))


class TestSlackNotifier(unittest.TestCase):
    """Test cases for SlackNotifier."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.notifier = SlackNotifier(
            webhook_url="https://hooks.slack.com/test",
            logger=self.logger,
        )

    @patch("src.integrations.notifications.requests.post")
    def test_send_success(self, mock_post):
        """Test successful Slack notification."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        event = NotificationEvent(
            event_type="test",
            title="Test Event",
            message="This is a test",
            severity="info",
        )

        result = self.notifier.send(event)

        self.assertTrue(result.success)
        self.assertEqual(result.channel, "slack")
        mock_post.assert_called_once()

    @patch("src.integrations.notifications.requests.post")
    def test_send_with_metadata_and_link(self, mock_post):
        """Test Slack notification with metadata and link."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        event = NotificationEvent(
            event_type="merge",
            title="PR Merged",
            message="PR has been merged",
            metadata={"pr_number": 123, "issue": "Closes #456"},
            severity="info",
            link="https://github.com/test/repo/pull/123",
        )

        result = self.notifier.send(event)

        self.assertTrue(result.success)

        # Verify blocks were built
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        self.assertIn("blocks", payload)
        blocks = payload["blocks"]

        # Should have header, content, metadata, button, footer
        self.assertGreater(len(blocks), 3)

    @patch("src.integrations.notifications.requests.post")
    def test_send_failure(self, mock_post):
        """Test Slack notification failure."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response

        event = NotificationEvent(
            event_type="test",
            title="Test Event",
            message="This is a test",
        )

        result = self.notifier.send(event)

        self.assertFalse(result.success)
        self.assertIn("400", result.error)

    @patch("src.integrations.notifications.requests.post")
    def test_send_exception(self, mock_post):
        """Test Slack notification exception handling."""
        mock_post.side_effect = Exception("Network error")

        event = NotificationEvent(
            event_type="test",
            title="Test Event",
            message="This is a test",
        )

        result = self.notifier.send(event)

        self.assertFalse(result.success)
        self.assertIn("Network error", result.error)


class TestEmailNotifier(unittest.TestCase):
    """Test cases for EmailNotifier."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.notifier = EmailNotifier(
            smtp_host="localhost",
            smtp_port=587,
            from_email="bot@example.com",
            to_email="user@example.com",
            username="bot",
            password="secret",
            logger=self.logger,
        )

    @patch("src.integrations.notifications.smtplib.SMTP")
    def test_send_success(self, mock_smtp_class):
        """Test successful email notification."""
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        event = NotificationEvent(
            event_type="test",
            title="Test Event",
            message="This is a test",
            severity="info",
        )

        result = self.notifier.send(event)

        self.assertTrue(result.success)
        self.assertEqual(result.channel, "email")
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("bot", "secret")
        mock_server.send_message.assert_called_once()

    @patch("src.integrations.notifications.smtplib.SMTP")
    def test_send_with_metadata(self, mock_smtp_class):
        """Test email with metadata."""
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        event = NotificationEvent(
            event_type="error",
            title="Error Occurred",
            message="An error happened",
            metadata={"error_code": "E123", "component": "processor"},
            severity="error",
            link="https://example.com/error",
        )

        result = self.notifier.send(event)

        self.assertTrue(result.success)

    @patch("src.integrations.notifications.smtplib.SMTP")
    def test_send_exception(self, mock_smtp_class):
        """Test email notification exception handling."""
        mock_smtp_class.side_effect = Exception("SMTP connection failed")

        event = NotificationEvent(
            event_type="test",
            title="Test Event",
            message="This is a test",
        )

        result = self.notifier.send(event)

        self.assertFalse(result.success)
        self.assertIn("SMTP connection failed", result.error)


class TestGitHubCommentNotifier(unittest.TestCase):
    """Test cases for GitHubCommentNotifier."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.github_client = Mock()
        self.notifier = GitHubCommentNotifier(
            github_client=self.github_client,
            logger=self.logger,
        )

    def test_send_success(self):
        """Test successful GitHub comment."""
        mock_issue = Mock()
        self.github_client.repo.get_issue.return_value = mock_issue

        event = NotificationEvent(
            event_type="progress",
            title="Work In Progress",
            message="Processing issue...",
            metadata={"issue_number": 123, "status": "in_progress"},
            severity="info",
        )

        result = self.notifier.send(event)

        self.assertTrue(result.success)
        self.assertEqual(result.channel, "github")
        self.github_client.repo.get_issue.assert_called_once_with(123)
        mock_issue.create_comment.assert_called_once()

    def test_send_without_issue_number(self):
        """Test GitHub comment without issue number."""
        event = NotificationEvent(
            event_type="test",
            title="Test Event",
            message="No issue number",
            metadata={},
        )

        result = self.notifier.send(event)

        self.assertFalse(result.success)
        self.assertIn("No issue/PR number", result.error)

    def test_send_exception(self):
        """Test GitHub comment exception handling."""
        self.github_client.repo.get_issue.side_effect = Exception("API error")

        event = NotificationEvent(
            event_type="test",
            title="Test Event",
            message="Test",
            metadata={"issue_number": 123},
        )

        result = self.notifier.send(event)

        self.assertFalse(result.success)
        self.assertIn("API error", result.error)


class TestNotificationManager(unittest.TestCase):
    """Test cases for NotificationManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.manager = NotificationManager(
            logger=self.logger,
            enabled_events={"error", "merge", "test"},
            rate_limit_per_hour=10,
            rate_limit_per_event_per_hour=3,
        )

    def test_initialization(self):
        """Test manager initialization."""
        self.assertIsNotNone(self.manager.logger)
        self.assertEqual(self.manager.enabled_events, {"error", "merge", "test"})

    def test_initialization_with_slack(self):
        """Test manager initialization with Slack."""
        manager = NotificationManager(
            logger=self.logger,
            enabled_events={"test"},
            slack_webhook="https://hooks.slack.com/test",
        )

        self.assertIn("slack", manager.channels)

    def test_initialization_with_email(self):
        """Test manager initialization with email."""
        email_config = {
            "smtp_host": "localhost",
            "smtp_port": 587,
            "from_email": "bot@example.com",
            "to_email": "user@example.com",
        }

        manager = NotificationManager(
            logger=self.logger,
            enabled_events={"test"},
            email_config=email_config,
        )

        self.assertIn("email", manager.channels)

    def test_notify_disabled_event(self):
        """Test notification of disabled event."""
        event = NotificationEvent(
            event_type="disabled_event",
            title="Test",
            message="Test",
        )

        results = self.manager.notify(event)

        self.assertEqual(len(results), 0)

    @patch("src.integrations.notifications.SlackNotifier.send")
    def test_notify_with_slack(self, mock_send):
        """Test notification with Slack channel."""
        mock_send.return_value = NotificationResult(
            success=True,
            channel="slack",
            event_type="test",
        )

        manager = NotificationManager(
            logger=self.logger,
            enabled_events={"test"},
            slack_webhook="https://hooks.slack.com/test",
        )

        event = NotificationEvent(
            event_type="test",
            title="Test Event",
            message="Test message",
        )

        results = manager.notify(event)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        mock_send.assert_called_once()

    def test_notify_rate_limited(self):
        """Test notification rate limiting."""
        manager = NotificationManager(
            logger=self.logger,
            enabled_events={"test"},
            rate_limit_per_event_per_hour=2,
        )

        event = NotificationEvent(
            event_type="test",
            title="Test",
            message="Test",
        )

        # Send 2 notifications (should succeed)
        manager.notify(event)
        manager.notify(event)

        # 3rd should be rate limited
        results = manager.notify(event)

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertTrue(results[0].rate_limited)

    def test_notify_error_helper(self):
        """Test notify_error helper method."""
        with patch.object(self.manager, "notify") as mock_notify:
            mock_notify.return_value = []

            self.manager.notify_error(
                title="Error Title",
                message="Error message",
                metadata={"code": "E123"},
                link="https://example.com",
            )

            mock_notify.assert_called_once()
            event = mock_notify.call_args[0][0]
            self.assertEqual(event.event_type, "error")
            self.assertEqual(event.severity, "error")

    def test_notify_merge_helper(self):
        """Test notify_merge helper method."""
        with patch.object(self.manager, "notify") as mock_notify:
            mock_notify.return_value = []

            self.manager.notify_merge(
                pr_number=123,
                pr_title="Add feature",
                issue_number=456,
                pr_url="https://github.com/test/repo/pull/123",
            )

            mock_notify.assert_called_once()
            event = mock_notify.call_args[0][0]
            self.assertEqual(event.event_type, "merge")
            self.assertEqual(event.metadata["pr_number"], 123)

    def test_notify_approval_required_helper(self):
        """Test notify_approval_required helper method."""
        with patch.object(self.manager, "notify") as mock_notify:
            mock_notify.return_value = []

            self.manager.notify_approval_required(
                title="Approval Needed",
                reason="High risk operation",
                metadata={"operation": "deploy"},
                link="https://example.com",
            )

            mock_notify.assert_called_once()
            event = mock_notify.call_args[0][0]
            self.assertEqual(event.event_type, "human_approval_required")
            self.assertEqual(event.severity, "warning")


class TestNotificationEvent(unittest.TestCase):
    """Test cases for NotificationEvent."""

    def test_to_dict(self):
        """Test NotificationEvent to_dict conversion."""
        event = NotificationEvent(
            event_type="test",
            title="Test Event",
            message="Test message",
            metadata={"key": "value"},
            severity="info",
            link="https://example.com",
        )

        event_dict = event.to_dict()

        self.assertEqual(event_dict["event_type"], "test")
        self.assertEqual(event_dict["title"], "Test Event")
        self.assertEqual(event_dict["metadata"], {"key": "value"})
        self.assertEqual(event_dict["severity"], "info")


class TestNotificationResult(unittest.TestCase):
    """Test cases for NotificationResult."""

    def test_to_dict(self):
        """Test NotificationResult to_dict conversion."""
        result = NotificationResult(
            success=True,
            channel="slack",
            event_type="test",
            rate_limited=False,
        )

        result_dict = result.to_dict()

        self.assertTrue(result_dict["success"])
        self.assertEqual(result_dict["channel"], "slack")
        self.assertFalse(result_dict["rate_limited"])


if __name__ == "__main__":
    unittest.main()
