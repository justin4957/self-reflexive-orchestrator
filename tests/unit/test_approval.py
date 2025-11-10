"""Unit tests for approval system."""

import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from src.core.logger import AuditLogger
from src.safety.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalSystem,
    RiskLevel,
)


class TestApprovalRequest(unittest.TestCase):
    """Test cases for ApprovalRequest."""

    def test_to_dict(self):
        """Test ApprovalRequest to_dict conversion."""
        request = ApprovalRequest(
            operation="merge_to_main",
            risk_level=RiskLevel.CRITICAL,
            concerns=["Affects production"],
            context={"pr_number": 123},
            timeout_hours=24.0,
        )

        request_dict = request.to_dict()

        self.assertEqual(request_dict["operation"], "merge_to_main")
        self.assertEqual(request_dict["risk_level"], "critical")
        self.assertEqual(request_dict["concerns"], ["Affects production"])
        self.assertEqual(request_dict["context"], {"pr_number": 123})
        self.assertEqual(request_dict["timeout_hours"], 24.0)

    def test_request_id_generation(self):
        """Test automatic request ID generation."""
        request = ApprovalRequest(
            operation="test_op",
            risk_level=RiskLevel.LOW,
            concerns=[],
        )

        self.assertTrue(request.request_id.startswith("approval-test_op-"))

    def test_timeout_at(self):
        """Test timeout_at property."""
        now = datetime.now(timezone.utc)
        request = ApprovalRequest(
            operation="test_op",
            risk_level=RiskLevel.LOW,
            concerns=[],
            timeout_hours=2.0,
            created_at=now,
        )

        expected_timeout = now + timedelta(hours=2.0)
        self.assertAlmostEqual(
            request.timeout_at.timestamp(),
            expected_timeout.timestamp(),
            delta=1.0,
        )

    def test_is_expired_false(self):
        """Test is_expired when not expired."""
        now = datetime.now(timezone.utc)
        request = ApprovalRequest(
            operation="test_op",
            risk_level=RiskLevel.LOW,
            concerns=[],
            timeout_hours=24.0,
            created_at=now,
        )

        self.assertFalse(request.is_expired)

    def test_is_expired_true(self):
        """Test is_expired when expired."""
        past = datetime.now(timezone.utc) - timedelta(hours=25)
        request = ApprovalRequest(
            operation="test_op",
            risk_level=RiskLevel.LOW,
            concerns=[],
            timeout_hours=24.0,
            created_at=past,
        )

        self.assertTrue(request.is_expired)

    def test_time_remaining_hours(self):
        """Test time_remaining_hours calculation."""
        now = datetime.now(timezone.utc)
        request = ApprovalRequest(
            operation="test_op",
            risk_level=RiskLevel.LOW,
            concerns=[],
            timeout_hours=10.0,
            created_at=now,
        )

        # Should be close to 10 hours
        self.assertAlmostEqual(request.time_remaining_hours, 10.0, delta=0.1)


class TestApprovalDecision(unittest.TestCase):
    """Test cases for ApprovalDecision."""

    def test_to_dict(self):
        """Test ApprovalDecision to_dict conversion."""
        decision = ApprovalDecision(
            approved=True,
            auto_approved=False,
            risk_level=RiskLevel.HIGH,
            rationale="Manual review approved",
            decided_by="admin",
            request_id="test-123",
        )

        decision_dict = decision.to_dict()

        self.assertTrue(decision_dict["approved"])
        self.assertFalse(decision_dict["auto_approved"])
        self.assertEqual(decision_dict["risk_level"], "high")
        self.assertEqual(decision_dict["rationale"], "Manual review approved")
        self.assertEqual(decision_dict["decided_by"], "admin")


class TestApprovalSystem(unittest.IsolatedAsyncioTestCase):
    """Test cases for ApprovalSystem."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.system = ApprovalSystem(
            logger=self.logger,
            auto_approve_low_risk=False,
            default_timeout_hours=24.0,
        )

    def test_initialization(self):
        """Test approval system initialization."""
        self.assertIsNotNone(self.system.logger)
        self.assertEqual(self.system.default_timeout_hours, 24.0)
        self.assertFalse(self.system.auto_approve_low_risk)

    def test_assess_risk_basic_critical(self):
        """Test basic risk assessment for critical operations."""
        risk_level, concerns = self.system._assess_risk_basic(
            "merge_to_main", {"pr_number": 123}
        )

        self.assertEqual(risk_level, RiskLevel.CRITICAL)
        self.assertIn("affects production", concerns[0].lower())

    def test_assess_risk_basic_high(self):
        """Test basic risk assessment for high risk operations."""
        risk_level, concerns = self.system._assess_risk_basic(
            "breaking_change", {"description": "API change"}
        )

        self.assertEqual(risk_level, RiskLevel.HIGH)
        self.assertIn("impact", concerns[0].lower())

    def test_assess_risk_basic_medium(self):
        """Test basic risk assessment for medium risk operations."""
        risk_level, concerns = self.system._assess_risk_basic(
            "configuration_change", {"file": "config.yaml"}
        )

        self.assertEqual(risk_level, RiskLevel.MEDIUM)

    def test_assess_risk_basic_low(self):
        """Test basic risk assessment for low risk operations."""
        risk_level, concerns = self.system._assess_risk_basic(
            "documentation_update", {}
        )

        self.assertEqual(risk_level, RiskLevel.LOW)

    def test_assess_risk_escalation_multiple_components(self):
        """Test risk escalation for multiple components."""
        risk_level, concerns = self.system._assess_risk_basic(
            "documentation_update", {"affects_multiple_components": True}
        )

        self.assertEqual(risk_level, RiskLevel.MEDIUM)
        self.assertTrue(any("multiple components" in c.lower() for c in concerns))

    def test_assess_risk_escalation_no_tests(self):
        """Test risk escalation when no tests available."""
        risk_level, concerns = self.system._assess_risk_basic(
            "configuration_change", {"no_tests_available": True}
        )

        self.assertEqual(risk_level, RiskLevel.HIGH)
        self.assertTrue(any("no automated tests" in c.lower() for c in concerns))

    def test_escalate_risk(self):
        """Test risk escalation logic."""
        self.assertEqual(self.system._escalate_risk(RiskLevel.LOW), RiskLevel.MEDIUM)
        self.assertEqual(self.system._escalate_risk(RiskLevel.MEDIUM), RiskLevel.HIGH)
        self.assertEqual(self.system._escalate_risk(RiskLevel.HIGH), RiskLevel.CRITICAL)
        self.assertEqual(
            self.system._escalate_risk(RiskLevel.CRITICAL), RiskLevel.CRITICAL
        )

    async def test_request_approval_auto_approve_low_risk(self):
        """Test auto-approval of low risk operations."""
        system = ApprovalSystem(
            logger=self.logger,
            auto_approve_low_risk=True,
        )

        decision = await system.request_approval(
            operation="documentation_update",
            context={},
            use_multi_agent_assessment=False,
        )

        self.assertTrue(decision.approved)
        self.assertTrue(decision.auto_approved)
        self.assertEqual(decision.risk_level, RiskLevel.LOW)
        self.assertEqual(decision.decided_by, "system")

    async def test_request_approval_timeout(self):
        """Test approval request timeout."""
        # Use very short timeout for testing
        decision = await self.system.request_approval(
            operation="test_operation",
            context={},
            timeout_hours=0.0001,  # ~0.36 seconds
            use_multi_agent_assessment=False,
        )

        self.assertFalse(decision.approved)
        self.assertFalse(decision.auto_approved)
        self.assertIn("timed out", decision.rationale.lower())
        self.assertEqual(decision.decided_by, "system")

    def test_approve_success(self):
        """Test successful approval."""
        # Create a pending request
        request = ApprovalRequest(
            operation="test_op",
            risk_level=RiskLevel.MEDIUM,
            concerns=["Test concern"],
        )
        self.system.pending_approvals[request.request_id] = request

        # Approve it
        success = self.system.approve(
            request_id=request.request_id,
            decided_by="admin",
            rationale="Approved for testing",
        )

        self.assertTrue(success)

    def test_approve_not_found(self):
        """Test approval of non-existent request."""
        success = self.system.approve(
            request_id="nonexistent",
            decided_by="admin",
            rationale="Should fail",
        )

        self.assertFalse(success)

    def test_approve_expired(self):
        """Test approval of expired request."""
        # Create expired request
        past = datetime.now(timezone.utc) - timedelta(hours=25)
        request = ApprovalRequest(
            operation="test_op",
            risk_level=RiskLevel.MEDIUM,
            concerns=[],
            timeout_hours=24.0,
            created_at=past,
        )
        self.system.pending_approvals[request.request_id] = request

        # Try to approve
        success = self.system.approve(
            request_id=request.request_id,
            decided_by="admin",
            rationale="Should fail - expired",
        )

        self.assertFalse(success)

    def test_deny_success(self):
        """Test successful denial."""
        # Create a pending request
        request = ApprovalRequest(
            operation="test_op",
            risk_level=RiskLevel.MEDIUM,
            concerns=["Test concern"],
        )
        self.system.pending_approvals[request.request_id] = request

        # Deny it
        success = self.system.deny(
            request_id=request.request_id,
            decided_by="admin",
            rationale="Risk too high",
        )

        self.assertTrue(success)

    def test_deny_not_found(self):
        """Test denial of non-existent request."""
        success = self.system.deny(
            request_id="nonexistent",
            decided_by="admin",
            rationale="Should fail",
        )

        self.assertFalse(success)

    def test_get_pending_approvals_empty(self):
        """Test getting pending approvals when none exist."""
        pending = self.system.get_pending_approvals()

        self.assertEqual(len(pending), 0)

    def test_get_pending_approvals_removes_expired(self):
        """Test that expired approvals are removed."""
        # Add valid request
        valid_request = ApprovalRequest(
            operation="valid",
            risk_level=RiskLevel.LOW,
            concerns=[],
            timeout_hours=24.0,
        )
        self.system.pending_approvals[valid_request.request_id] = valid_request

        # Add expired request
        past = datetime.now(timezone.utc) - timedelta(hours=25)
        expired_request = ApprovalRequest(
            operation="expired",
            risk_level=RiskLevel.LOW,
            concerns=[],
            timeout_hours=24.0,
            created_at=past,
        )
        self.system.pending_approvals[expired_request.request_id] = expired_request

        # Get pending (should remove expired)
        pending = self.system.get_pending_approvals()

        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].operation, "valid")
        self.assertNotIn(expired_request.request_id, self.system.pending_approvals)

    def test_get_approval_history_empty(self):
        """Test getting approval history when empty."""
        history = self.system.get_approval_history()

        self.assertEqual(len(history), 0)

    def test_get_approval_history_with_limit(self):
        """Test getting approval history with limit."""
        # Add some decisions
        for i in range(5):
            decision = ApprovalDecision(
                approved=True,
                auto_approved=False,
                risk_level=RiskLevel.LOW,
                rationale=f"Test {i}",
                decided_by="admin",
                request_id=f"test-{i}",
            )
            self.system.approval_history.append(decision)

        # Get limited history
        history = self.system.get_approval_history(limit=3)

        self.assertEqual(len(history), 3)

    def test_check_pending_approvals_summary(self):
        """Test checking pending approvals summary."""
        # Add requests with different risk levels
        low_request = ApprovalRequest(
            operation="low_op",
            risk_level=RiskLevel.LOW,
            concerns=[],
        )
        high_request = ApprovalRequest(
            operation="high_op",
            risk_level=RiskLevel.HIGH,
            concerns=[],
        )
        critical_request = ApprovalRequest(
            operation="critical_op",
            risk_level=RiskLevel.CRITICAL,
            concerns=[],
        )

        self.system.pending_approvals[low_request.request_id] = low_request
        self.system.pending_approvals[high_request.request_id] = high_request
        self.system.pending_approvals[critical_request.request_id] = critical_request

        summary = self.system.check_pending_approvals()

        self.assertEqual(summary["total_pending"], 3)
        self.assertEqual(summary["by_risk_level"]["low"], 1)
        self.assertEqual(summary["by_risk_level"]["high"], 1)
        self.assertEqual(summary["by_risk_level"]["critical"], 1)
        self.assertEqual(summary["by_operation"]["low_op"], 1)
        self.assertEqual(summary["by_operation"]["high_op"], 1)

    def test_check_pending_approvals_expiring_soon(self):
        """Test detection of approvals expiring soon."""
        # Add request expiring in 30 minutes
        soon = datetime.now(timezone.utc) - timedelta(hours=23.5)
        expiring_request = ApprovalRequest(
            operation="expiring",
            risk_level=RiskLevel.HIGH,
            concerns=[],
            timeout_hours=24.0,
            created_at=soon,
        )
        self.system.pending_approvals[expiring_request.request_id] = expiring_request

        summary = self.system.check_pending_approvals()

        self.assertEqual(len(summary["expiring_soon"]), 1)
        self.assertEqual(summary["expiring_soon"][0]["operation"], "expiring")
        self.assertLess(summary["expiring_soon"][0]["time_remaining_minutes"], 60)

    def test_synthesize_risk_assessments_empty(self):
        """Test risk synthesis with empty responses."""
        risk_level, concerns = self.system._synthesize_risk_assessments([])

        self.assertEqual(risk_level, RiskLevel.MEDIUM)
        self.assertEqual(concerns, ["No risk assessment available"])

    def test_synthesize_risk_assessments_conservative(self):
        """Test conservative risk synthesis (highest risk wins)."""
        responses = [
            {"content": "Risk Level: low\n- Routine change"},
            {"content": "Risk Level: critical\n- Affects production systems"},
            {"content": "Risk Level: medium\n- Requires review"},
        ]

        risk_level, concerns = self.system._synthesize_risk_assessments(responses)

        # Should pick critical (highest risk)
        self.assertEqual(risk_level, RiskLevel.CRITICAL)

    def test_synthesize_risk_assessments_extract_concerns(self):
        """Test concern extraction from responses."""
        responses = [
            {"content": "Risk: high\n- Security implications\n- Breaking changes"},
            {
                "content": "Risk: medium\nconcern: No test coverage\n• Affects multiple services"
            },
        ]

        risk_level, concerns = self.system._synthesize_risk_assessments(responses)

        # Should extract concerns from both responses
        self.assertGreater(len(concerns), 0)

    def test_build_risk_assessment_prompt(self):
        """Test building risk assessment prompt."""
        prompt = self.system._build_risk_assessment_prompt(
            "merge_to_main",
            {"pr_number": 123, "files_changed": 5},
        )

        self.assertIn("merge_to_main", prompt)
        self.assertIn("pr_number", prompt)
        self.assertIn("files_changed", prompt)
        self.assertIn("risk level", prompt.lower())

    def test_format_context(self):
        """Test context formatting."""
        context = {"key1": "value1", "key2": 42}

        formatted = self.system._format_context(context)

        self.assertIn("key1: value1", formatted)
        self.assertIn("key2: 42", formatted)

    def test_format_context_empty(self):
        """Test formatting empty context."""
        formatted = self.system._format_context({})

        self.assertEqual(formatted, "No additional context")


if __name__ == "__main__":
    unittest.main()
