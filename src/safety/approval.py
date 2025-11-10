"""Human approval system for sensitive operations.

Provides approval workflows with multi-agent risk assessment,
multiple approval methods (CLI, GitHub, Slack), and timeout handling.
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..core.logger import AuditLogger
from ..integrations.multi_agent_coder_client import (MultiAgentCoderClient,
                                                     MultiAgentStrategy)


class RiskLevel(Enum):
    """Risk levels for operations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalStatus(Enum):
    """Approval request status."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class ApprovalRequest:
    """Request for human approval of an operation.

    Attributes:
        operation: Type of operation requiring approval
        risk_level: Assessed risk level
        concerns: List of specific concerns raised
        context: Additional context about the operation
        timeout_hours: Hours until request times out
        created_at: Timestamp when request was created
        request_id: Unique identifier for this request
    """

    operation: str
    risk_level: RiskLevel
    concerns: List[str]
    context: Dict[str, Any] = field(default_factory=dict)
    timeout_hours: float = 24.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: str = ""

    def __post_init__(self):
        """Generate request ID if not provided."""
        if not self.request_id:
            timestamp = int(self.created_at.timestamp())
            self.request_id = f"approval-{self.operation}-{timestamp}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "request_id": self.request_id,
            "operation": self.operation,
            "risk_level": self.risk_level.value,
            "concerns": self.concerns,
            "context": self.context,
            "timeout_hours": self.timeout_hours,
            "created_at": self.created_at.isoformat(),
        }

    @property
    def timeout_at(self) -> datetime:
        """Calculate timeout timestamp."""
        return self.created_at + timedelta(hours=self.timeout_hours)

    @property
    def is_expired(self) -> bool:
        """Check if request has expired."""
        return datetime.now(timezone.utc) > self.timeout_at

    @property
    def time_remaining_hours(self) -> float:
        """Calculate remaining time in hours."""
        remaining = self.timeout_at - datetime.now(timezone.utc)
        return max(0.0, remaining.total_seconds() / 3600)


@dataclass
class ApprovalDecision:
    """Decision on an approval request.

    Attributes:
        approved: Whether operation was approved
        auto_approved: Whether approved automatically
        risk_level: Final assessed risk level
        rationale: Explanation for the decision
        decided_by: Who made the decision
        decided_at: When decision was made
        request_id: ID of the approval request
    """

    approved: bool
    auto_approved: bool
    risk_level: RiskLevel
    rationale: str
    decided_by: str
    decided_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "request_id": self.request_id,
            "approved": self.approved,
            "auto_approved": self.auto_approved,
            "risk_level": self.risk_level.value,
            "rationale": self.rationale,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at.isoformat(),
        }


class ApprovalSystem:
    """Manages human approval workflows for sensitive operations.

    Features:
    - Multi-agent risk assessment
    - Multiple approval methods (CLI, GitHub, Slack)
    - Approval timeout handling
    - Approval history tracking
    - Conservative risk synthesis
    """

    def __init__(
        self,
        logger: AuditLogger,
        multi_agent_client: Optional[MultiAgentCoderClient] = None,
        notification_callback: Optional[Callable] = None,
        auto_approve_low_risk: bool = False,
        default_timeout_hours: float = 24.0,
    ):
        """Initialize approval system.

        Args:
            logger: Audit logger
            multi_agent_client: Multi-agent coder client for risk assessment
            notification_callback: Function to call for sending notifications
            auto_approve_low_risk: Whether to auto-approve low risk operations
            default_timeout_hours: Default timeout for approval requests
        """
        self.logger = logger
        self.multi_agent_client = multi_agent_client
        self.notification_callback = notification_callback
        self.auto_approve_low_risk = auto_approve_low_risk
        self.default_timeout_hours = default_timeout_hours

        # Track pending and completed approvals
        self.pending_approvals: Dict[str, ApprovalRequest] = {}
        self.approval_history: List[ApprovalDecision] = []

        # Approval decision callbacks by request_id
        self._approval_futures: Dict[str, asyncio.Future] = {}

        self.logger.info("approval_system_initialized")

    async def request_approval(
        self,
        operation: str,
        context: Dict[str, Any],
        timeout_hours: Optional[float] = None,
        use_multi_agent_assessment: bool = True,
    ) -> ApprovalDecision:
        """Request approval for an operation.

        Args:
            operation: Type of operation requiring approval
            context: Context about the operation
            timeout_hours: Override default timeout
            use_multi_agent_assessment: Whether to use multi-agent risk assessment

        Returns:
            ApprovalDecision with the outcome
        """
        self.logger.info(
            "approval_requested",
            operation=operation,
            context=context,
        )

        # Assess risk using multi-agent system if available
        if use_multi_agent_assessment and self.multi_agent_client:
            risk_level, concerns = await self._assess_risk_multi_agent(
                operation, context
            )
        else:
            risk_level, concerns = self._assess_risk_basic(operation, context)

        # Create approval request
        request = ApprovalRequest(
            operation=operation,
            risk_level=risk_level,
            concerns=concerns,
            context=context,
            timeout_hours=timeout_hours or self.default_timeout_hours,
        )

        # Auto-approve low risk if configured
        if self.auto_approve_low_risk and risk_level == RiskLevel.LOW:
            decision = ApprovalDecision(
                approved=True,
                auto_approved=True,
                risk_level=risk_level,
                rationale="Auto-approved: low risk operation",
                decided_by="system",
                request_id=request.request_id,
            )

            self.logger.info(
                "approval_auto_approved",
                request_id=request.request_id,
                operation=operation,
                risk_level=risk_level.value,
            )

            self.approval_history.append(decision)
            return decision

        # Store pending approval
        self.pending_approvals[request.request_id] = request

        # Send notifications
        await self._notify_approval_needed(request)

        # Wait for approval or timeout
        decision = await self._wait_for_approval(request)

        # Record decision
        self.approval_history.append(decision)

        # Remove from pending
        self.pending_approvals.pop(request.request_id, None)

        self.logger.info(
            "approval_decided",
            request_id=request.request_id,
            operation=operation,
            approved=decision.approved,
            decided_by=decision.decided_by,
        )

        return decision

    async def _assess_risk_multi_agent(
        self, operation: str, context: Dict[str, Any]
    ) -> tuple[RiskLevel, List[str]]:
        """Assess risk using multi-agent system.

        Args:
            operation: Operation type
            context: Operation context

        Returns:
            Tuple of (risk_level, concerns)
        """
        self.logger.info("multi_agent_risk_assessment_started", operation=operation)

        # Build risk assessment prompt
        prompt = self._build_risk_assessment_prompt(operation, context)

        try:
            # Query multi-agent system with ALL strategy for multiple perspectives
            result = await self.multi_agent_client.query(
                prompt=prompt,
                strategy=MultiAgentStrategy.ALL,
            )

            # Parse and synthesize risk assessments
            risk_level, concerns = self._synthesize_risk_assessments(
                result.get("responses", [])
            )

            self.logger.info(
                "multi_agent_risk_assessment_completed",
                operation=operation,
                risk_level=risk_level.value,
                concerns_count=len(concerns),
            )

            return risk_level, concerns

        except Exception as e:
            self.logger.error(
                "multi_agent_risk_assessment_failed",
                operation=operation,
                error=str(e),
            )

            # Fall back to basic assessment
            return self._assess_risk_basic(operation, context)

    def _assess_risk_basic(
        self, operation: str, context: Dict[str, Any]
    ) -> tuple[RiskLevel, List[str]]:
        """Basic rule-based risk assessment.

        Args:
            operation: Operation type
            context: Operation context

        Returns:
            Tuple of (risk_level, concerns)
        """
        concerns = []

        # Critical operations
        if operation in ["merge_to_main", "production_deploy"]:
            risk_level = RiskLevel.CRITICAL
            concerns.append(f"{operation} affects production systems")

        # High risk operations
        elif operation in ["breaking_change", "security_related", "database_migration"]:
            risk_level = RiskLevel.HIGH
            concerns.append(f"{operation} may impact system stability")

        # Medium risk operations
        elif operation in ["configuration_change", "dependency_update"]:
            risk_level = RiskLevel.MEDIUM
            concerns.append(f"{operation} requires careful review")

        # Low risk operations
        else:
            risk_level = RiskLevel.LOW
            concerns.append(f"{operation} is routine")

        # Check context for additional risk factors
        if context.get("affects_multiple_components", False):
            risk_level = self._escalate_risk(risk_level)
            concerns.append("Affects multiple components")

        if context.get("no_tests_available", False):
            risk_level = self._escalate_risk(risk_level)
            concerns.append("No automated tests available")

        if context.get("time_sensitive", False):
            concerns.append("Time-sensitive operation")

        return risk_level, concerns

    def _build_risk_assessment_prompt(
        self, operation: str, context: Dict[str, Any]
    ) -> str:
        """Build prompt for multi-agent risk assessment.

        Args:
            operation: Operation type
            context: Operation context

        Returns:
            Risk assessment prompt
        """
        return f"""Assess the risk level for the following operation:

Operation: {operation}

Context:
{self._format_context(context)}

Please analyze this operation and provide:
1. Risk Level (low/medium/high/critical)
2. Specific concerns or risks
3. Recommended safeguards

Consider:
- Impact on production systems
- Reversibility of changes
- Testing coverage
- Complexity and scope
- Security implications
- Compliance requirements

Provide a structured risk assessment."""

    def _format_context(self, context: Dict[str, Any]) -> str:
        """Format context for display.

        Args:
            context: Context dictionary

        Returns:
            Formatted context string
        """
        lines = []
        for key, value in context.items():
            lines.append(f"- {key}: {value}")
        return "\n".join(lines) if lines else "No additional context"

    def _synthesize_risk_assessments(
        self, responses: List[Dict[str, Any]]
    ) -> tuple[RiskLevel, List[str]]:
        """Synthesize multiple risk assessments using conservative approach.

        Takes the highest risk level from all assessments.

        Args:
            responses: List of responses from multi-agent system

        Returns:
            Tuple of (risk_level, concerns)
        """
        if not responses:
            return RiskLevel.MEDIUM, ["No risk assessment available"]

        # Extract risk levels and concerns from responses
        risk_levels = []
        all_concerns = []

        risk_keywords = {
            "critical": RiskLevel.CRITICAL,
            "high": RiskLevel.HIGH,
            "medium": RiskLevel.MEDIUM,
            "low": RiskLevel.LOW,
        }

        for response in responses:
            content = response.get("content", "").lower()

            # Find highest risk level mentioned
            for keyword, level in risk_keywords.items():
                if keyword in content:
                    risk_levels.append(level)
                    break

            # Extract concerns (lines starting with "concern:" or "-")
            lines = response.get("content", "").split("\n")
            for line in lines:
                line = line.strip()
                if line.startswith(("concern:", "-", "•")):
                    concern = line.lstrip("concern:-•").strip()
                    if concern:
                        all_concerns.append(concern)

        # Conservative synthesis: take highest risk
        if not risk_levels:
            risk_levels = [RiskLevel.MEDIUM]

        # Order by severity
        severity_order = [
            RiskLevel.CRITICAL,
            RiskLevel.HIGH,
            RiskLevel.MEDIUM,
            RiskLevel.LOW,
        ]

        final_risk = RiskLevel.LOW
        for level in severity_order:
            if level in risk_levels:
                final_risk = level
                break

        # Deduplicate concerns
        unique_concerns = list(set(all_concerns))

        if not unique_concerns:
            unique_concerns = ["Multiple perspectives assessed"]

        return final_risk, unique_concerns

    def _escalate_risk(self, current_risk: RiskLevel) -> RiskLevel:
        """Escalate risk level by one step.

        Args:
            current_risk: Current risk level

        Returns:
            Escalated risk level
        """
        escalation_map = {
            RiskLevel.LOW: RiskLevel.MEDIUM,
            RiskLevel.MEDIUM: RiskLevel.HIGH,
            RiskLevel.HIGH: RiskLevel.CRITICAL,
            RiskLevel.CRITICAL: RiskLevel.CRITICAL,
        }

        return escalation_map[current_risk]

    async def _notify_approval_needed(self, request: ApprovalRequest):
        """Send notifications about approval request.

        Args:
            request: Approval request
        """
        if not self.notification_callback:
            return

        try:
            await self.notification_callback(
                event_type="approval_needed",
                data={
                    "request_id": request.request_id,
                    "operation": request.operation,
                    "risk_level": request.risk_level.value,
                    "concerns": request.concerns,
                    "timeout_hours": request.timeout_hours,
                    "context": request.context,
                },
            )

            self.logger.info(
                "approval_notification_sent", request_id=request.request_id
            )

        except Exception as e:
            self.logger.error(
                "approval_notification_failed",
                request_id=request.request_id,
                error=str(e),
            )

    async def _wait_for_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        """Wait for approval decision or timeout.

        Args:
            request: Approval request

        Returns:
            ApprovalDecision
        """
        # Create future for this approval
        future = asyncio.Future()
        self._approval_futures[request.request_id] = future

        try:
            # Wait for decision or timeout
            timeout_seconds = request.timeout_hours * 3600
            decision = await asyncio.wait_for(future, timeout=timeout_seconds)
            return decision

        except asyncio.TimeoutError:
            # Request timed out
            decision = ApprovalDecision(
                approved=False,
                auto_approved=False,
                risk_level=request.risk_level,
                rationale=f"Approval request timed out after {request.timeout_hours} hours",
                decided_by="system",
                request_id=request.request_id,
            )

            self.logger.warning(
                "approval_timeout",
                request_id=request.request_id,
                operation=request.operation,
            )

            return decision

        finally:
            # Clean up future
            self._approval_futures.pop(request.request_id, None)

    def approve(self, request_id: str, decided_by: str, rationale: str = "") -> bool:
        """Approve a pending request.

        Args:
            request_id: ID of approval request
            decided_by: Who is approving
            rationale: Reason for approval

        Returns:
            True if approved successfully
        """
        request = self.pending_approvals.get(request_id)

        if not request:
            self.logger.warning(
                "approval_not_found", request_id=request_id, action="approve"
            )
            return False

        if request.is_expired:
            self.logger.warning(
                "approval_expired", request_id=request_id, action="approve"
            )
            return False

        decision = ApprovalDecision(
            approved=True,
            auto_approved=False,
            risk_level=request.risk_level,
            rationale=rationale or f"Approved by {decided_by}",
            decided_by=decided_by,
            request_id=request_id,
        )

        # Resolve future if exists
        future = self._approval_futures.get(request_id)
        if future and not future.done():
            future.set_result(decision)

        self.logger.info(
            "approval_approved",
            request_id=request_id,
            decided_by=decided_by,
        )

        return True

    def deny(self, request_id: str, decided_by: str, rationale: str = "") -> bool:
        """Deny a pending request.

        Args:
            request_id: ID of approval request
            decided_by: Who is denying
            rationale: Reason for denial

        Returns:
            True if denied successfully
        """
        request = self.pending_approvals.get(request_id)

        if not request:
            self.logger.warning(
                "approval_not_found", request_id=request_id, action="deny"
            )
            return False

        if request.is_expired:
            self.logger.warning(
                "approval_expired", request_id=request_id, action="deny"
            )
            return False

        decision = ApprovalDecision(
            approved=False,
            auto_approved=False,
            risk_level=request.risk_level,
            rationale=rationale or f"Denied by {decided_by}",
            decided_by=decided_by,
            request_id=request_id,
        )

        # Resolve future if exists
        future = self._approval_futures.get(request_id)
        if future and not future.done():
            future.set_result(decision)

        self.logger.info(
            "approval_denied",
            request_id=request_id,
            decided_by=decided_by,
        )

        return True

    def get_pending_approvals(self) -> List[ApprovalRequest]:
        """Get all pending approval requests.

        Returns:
            List of pending requests
        """
        # Remove expired requests
        expired_ids = [
            req_id for req_id, req in self.pending_approvals.items() if req.is_expired
        ]

        for req_id in expired_ids:
            self.pending_approvals.pop(req_id)
            self.logger.info("approval_expired_removed", request_id=req_id)

        return list(self.pending_approvals.values())

    def get_approval_history(
        self, limit: Optional[int] = None
    ) -> List[ApprovalDecision]:
        """Get approval history.

        Args:
            limit: Optional limit on number of records

        Returns:
            List of approval decisions
        """
        history = sorted(
            self.approval_history, key=lambda d: d.decided_at, reverse=True
        )

        if limit:
            return history[:limit]

        return history

    def check_pending_approvals(self) -> Dict[str, Any]:
        """Check status of all pending approvals.

        Returns:
            Summary of pending approvals
        """
        pending = self.get_pending_approvals()

        summary = {
            "total_pending": len(pending),
            "by_risk_level": {},
            "by_operation": {},
            "expiring_soon": [],
        }

        for request in pending:
            # Count by risk level
            risk = request.risk_level.value
            summary["by_risk_level"][risk] = summary["by_risk_level"].get(risk, 0) + 1

            # Count by operation
            op = request.operation
            summary["by_operation"][op] = summary["by_operation"].get(op, 0) + 1

            # Check if expiring soon (< 1 hour)
            if request.time_remaining_hours < 1.0:
                summary["expiring_soon"].append(
                    {
                        "request_id": request.request_id,
                        "operation": request.operation,
                        "time_remaining_minutes": request.time_remaining_hours * 60,
                    }
                )

        return summary
