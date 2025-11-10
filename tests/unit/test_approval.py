"""Unit tests for ApprovalManager."""

import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta

from src.safety.approval import (
    ApprovalManager,
    ApprovalRequest,
    ApprovalStatus,
)
from src.core.logger import AuditLogger


class TestApprovalManager(unittest.TestCase):
    """Test cases for ApprovalManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.notification_callback = Mock()

        self.manager = ApprovalManager(
            logger=self.logger,
            notification_callback=self.notification_callback,
            approval_timeout=3600,
        )

    def test_initialization(self):
        """Test manager initialization."""
        self.assertEqual(self.manager.approval_timeout, 3600)
        self.assertEqual(len(self.manager.pending_approvals), 0)
        self.assertEqual(len(self.manager.approval_history), 0)
        self.assertEqual(self.manager.total_requests, 0)
        self.assertEqual(self.manager.total_approved, 0)
        self.assertEqual(self.manager.total_denied, 0)

    def test_request_approval(self):
        """Test creating an approval request."""
        request = self.manager.request_approval(
            action="merge PR #123",
            reason="PR requires manual review",
            resource_type="pr",
            resource_id="123",
            metadata={"pr_title": "Test PR"},
        )

        self.assertIsInstance(request, ApprovalRequest)
        self.assertEqual(request.action, "merge PR #123")
        self.assertEqual(request.reason, "PR requires manual review")
        self.assertEqual(request.status, ApprovalStatus.PENDING)
        self.assertEqual(len(self.manager.pending_approvals), 1)
        self.assertEqual(self.manager.total_requests, 1)

        # Check notification callback was called
        self.notification_callback.assert_called_once_with(request)

        # Check audit log was called
        self.logger.human_approval_requested.assert_called_once()

    def test_approve_request(self):
        """Test approving a pending request."""
        # Create request
        request = self.manager.request_approval(
            action="merge PR #123",
            reason="Manual review",
            resource_type="pr",
            resource_id="123",
        )

        request_id = request.request_id

        # Approve it
        approved_request = self.manager.approve(
            request_id=request_id,
            approver="user@example.com",
            note="LGTM",
        )

        self.assertEqual(approved_request.status, ApprovalStatus.APPROVED)
        self.assertEqual(approved_request.approver, "user@example.com")
        self.assertEqual(approved_request.response_note, "LGTM")
        self.assertIsNotNone(approved_request.responded_at)

        # Should be moved to history
        self.assertEqual(len(self.manager.pending_approvals), 0)
        self.assertEqual(len(self.manager.approval_history), 1)
        self.assertEqual(self.manager.total_approved, 1)

        # Check audit log
        self.logger.audit.assert_called()

    def test_approve_nonexistent_request(self):
        """Test approving a request that doesn't exist."""
        with self.assertRaises(ValueError) as context:
            self.manager.approve(
                request_id="nonexistent",
                approver="user@example.com",
            )

        self.assertIn("not found", str(context.exception))

    def test_approve_non_pending_request(self):
        """Test approving a request that's not pending."""
        # Create and approve a request
        request = self.manager.request_approval(
            action="test",
            reason="test",
            resource_type="test",
            resource_id="1",
        )

        request_id = request.request_id
        self.manager.approve(request_id, "user@example.com")

        # Try to approve again - should fail because it's no longer in pending
        with self.assertRaises(ValueError) as context:
            self.manager.approve(request_id, "user@example.com")

        # Request is moved to history, so error is "not found" in pending
        self.assertIn("not found", str(context.exception))

    def test_deny_request(self):
        """Test denying a pending request."""
        # Create request
        request = self.manager.request_approval(
            action="deploy to production",
            reason="High risk deployment",
            resource_type="deployment",
            resource_id="prod-123",
        )

        request_id = request.request_id

        # Deny it
        denied_request = self.manager.deny(
            request_id=request_id,
            approver="admin@example.com",
            reason="Need more testing",
        )

        self.assertEqual(denied_request.status, ApprovalStatus.DENIED)
        self.assertEqual(denied_request.approver, "admin@example.com")
        self.assertEqual(denied_request.response_note, "Need more testing")
        self.assertIsNotNone(denied_request.responded_at)

        # Should be moved to history
        self.assertEqual(len(self.manager.pending_approvals), 0)
        self.assertEqual(len(self.manager.approval_history), 1)
        self.assertEqual(self.manager.total_denied, 1)

    def test_cancel_request(self):
        """Test cancelling a pending request."""
        # Create request
        request = self.manager.request_approval(
            action="test action",
            reason="test reason",
            resource_type="test",
            resource_id="1",
        )

        request_id = request.request_id

        # Cancel it
        cancelled_request = self.manager.cancel(
            request_id=request_id,
            reason="No longer needed",
        )

        self.assertEqual(cancelled_request.status, ApprovalStatus.CANCELLED)
        self.assertEqual(cancelled_request.response_note, "No longer needed")
        self.assertIsNotNone(cancelled_request.responded_at)

        # Should be moved to history
        self.assertEqual(len(self.manager.pending_approvals), 0)
        self.assertEqual(len(self.manager.approval_history), 1)

    def test_expire_old_requests(self):
        """Test expiring old pending requests."""
        # Create a request
        request = self.manager.request_approval(
            action="test action",
            reason="test reason",
            resource_type="test",
            resource_id="1",
        )

        # Manually set requested_at to be old (more than timeout)
        old_time = datetime.now(timezone.utc) - timedelta(seconds=3601)
        request.requested_at = old_time
        self.manager.pending_approvals[request.request_id] = request

        # Expire old requests
        expired = self.manager.expire_old_requests()

        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0].status, ApprovalStatus.EXPIRED)
        self.assertEqual(len(self.manager.pending_approvals), 0)
        self.assertEqual(len(self.manager.approval_history), 1)
        self.assertEqual(self.manager.total_expired, 1)

    def test_expire_old_requests_none_expired(self):
        """Test expiring when no requests are old."""
        # Create a recent request
        request = self.manager.request_approval(
            action="test action",
            reason="test reason",
            resource_type="test",
            resource_id="1",
        )

        # Expire old requests
        expired = self.manager.expire_old_requests()

        # Nothing should expire
        self.assertEqual(len(expired), 0)
        self.assertEqual(len(self.manager.pending_approvals), 1)

    def test_get_pending_requests(self):
        """Test getting all pending requests."""
        # Create multiple requests
        request1 = self.manager.request_approval(
            action="action 1",
            reason="reason 1",
            resource_type="pr",
            resource_id="1",
        )

        request2 = self.manager.request_approval(
            action="action 2",
            reason="reason 2",
            resource_type="pr",
            resource_id="2",
        )

        pending = self.manager.get_pending_requests()

        self.assertEqual(len(pending), 2)
        self.assertIn(request1, pending)
        self.assertIn(request2, pending)

    def test_get_request_pending(self):
        """Test getting a specific pending request."""
        request = self.manager.request_approval(
            action="test action",
            reason="test reason",
            resource_type="test",
            resource_id="1",
        )

        found = self.manager.get_request(request.request_id)

        self.assertIsNotNone(found)
        self.assertEqual(found.request_id, request.request_id)

    def test_get_request_from_history(self):
        """Test getting a request from history."""
        request = self.manager.request_approval(
            action="test action",
            reason="test reason",
            resource_type="test",
            resource_id="1",
        )

        request_id = request.request_id
        self.manager.approve(request_id, "user@example.com")

        # Request should now be in history
        found = self.manager.get_request(request_id)

        self.assertIsNotNone(found)
        self.assertEqual(found.request_id, request_id)
        self.assertEqual(found.status, ApprovalStatus.APPROVED)

    def test_get_request_not_found(self):
        """Test getting a nonexistent request."""
        found = self.manager.get_request("nonexistent")

        self.assertIsNone(found)

    def test_get_statistics(self):
        """Test getting statistics."""
        # Create and process several requests
        request1 = self.manager.request_approval("action1", "reason1", "pr", "1")
        request2 = self.manager.request_approval("action2", "reason2", "pr", "2")
        request3 = self.manager.request_approval("action3", "reason3", "pr", "3")

        self.manager.approve(request1.request_id, "user1")
        self.manager.approve(request2.request_id, "user2")
        self.manager.deny(request3.request_id, "user3")

        stats = self.manager.get_statistics()

        self.assertEqual(stats["total_requests"], 3)
        self.assertEqual(stats["total_approved"], 2)
        self.assertEqual(stats["total_denied"], 1)
        self.assertEqual(stats["total_expired"], 0)
        self.assertEqual(stats["pending_count"], 0)
        self.assertEqual(stats["approval_rate"], 2 / 3)

    def test_get_statistics_no_requests(self):
        """Test statistics when no requests have been made."""
        stats = self.manager.get_statistics()

        self.assertEqual(stats["total_requests"], 0)
        self.assertEqual(stats["approval_rate"], 0.0)

    def test_reset_statistics(self):
        """Test resetting statistics."""
        # Create some requests
        request = self.manager.request_approval("action", "reason", "pr", "1")
        self.manager.approve(request.request_id, "user")

        # Reset
        self.manager.reset_statistics()

        self.assertEqual(self.manager.total_requests, 0)
        self.assertEqual(self.manager.total_approved, 0)
        self.assertEqual(self.manager.total_denied, 0)
        self.assertEqual(self.manager.total_expired, 0)

    def test_notification_callback_failure(self):
        """Test handling notification callback failure."""
        # Create manager with failing callback
        failing_callback = Mock(side_effect=Exception("Notification failed"))
        manager = ApprovalManager(
            logger=self.logger,
            notification_callback=failing_callback,
        )

        # Should not raise exception
        request = manager.request_approval(
            action="test",
            reason="test",
            resource_type="test",
            resource_id="1",
        )

        # Request should still be created
        self.assertIsNotNone(request)
        self.assertEqual(len(manager.pending_approvals), 1)

        # Error should be logged
        self.logger.error.assert_called_once()

    def test_approval_request_dataclass(self):
        """Test ApprovalRequest dataclass."""
        request = ApprovalRequest(
            request_id="test-123",
            action="test action",
            reason="test reason",
            resource_type="pr",
            resource_id="456",
            status=ApprovalStatus.APPROVED,
            approver="user@example.com",
            response_note="Looks good",
            metadata={"key": "value"},
        )

        request_dict = request.to_dict()

        self.assertEqual(request_dict["request_id"], "test-123")
        self.assertEqual(request_dict["action"], "test action")
        self.assertEqual(request_dict["status"], "approved")
        self.assertEqual(request_dict["approver"], "user@example.com")
        self.assertEqual(request_dict["response_note"], "Looks good")
        self.assertEqual(request_dict["metadata"]["key"], "value")


if __name__ == "__main__":
    unittest.main()
