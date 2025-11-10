"""Human approval management for safety gates.

Handles requesting and tracking human approval for safety-critical operations.
"""

from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import uuid

from ..core.logger import AuditLogger, EventType


class ApprovalStatus(Enum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class ApprovalRequest:
    """An approval request for a safety-critical operation."""

    request_id: str
    action: str
    reason: str
    resource_type: str
    resource_id: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    responded_at: Optional[datetime] = None
    approver: Optional[str] = None
    response_note: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "request_id": self.request_id,
            "action": self.action,
            "reason": self.reason,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "status": self.status.value,
            "requested_at": self.requested_at.isoformat(),
            "responded_at": (
                self.responded_at.isoformat() if self.responded_at else None
            ),
            "approver": self.approver,
            "response_note": self.response_note,
            "metadata": self.metadata,
        }


class ApprovalManager:
    """Manages human approval requests for safety-critical operations.

    Responsibilities:
    - Create approval requests
    - Track pending approvals
    - Handle approval responses (approve/deny)
    - Expire old requests
    - Notify appropriate channels
    - Log all approval decisions
    """

    def __init__(
        self,
        logger: AuditLogger,
        notification_callback: Optional[Callable[[ApprovalRequest], None]] = None,
        approval_timeout: int = 3600,  # 1 hour default
    ):
        """Initialize approval manager.

        Args:
            logger: Audit logger
            notification_callback: Optional callback to notify about new approvals
            approval_timeout: Seconds before approval request expires
        """
        self.logger = logger
        self.notification_callback = notification_callback
        self.approval_timeout = approval_timeout

        # Track pending approvals
        self.pending_approvals: Dict[str, ApprovalRequest] = {}
        self.approval_history: List[ApprovalRequest] = []

        # Statistics
        self.total_requests = 0
        self.total_approved = 0
        self.total_denied = 0
        self.total_expired = 0

    def request_approval(
        self,
        action: str,
        reason: str,
        resource_type: str,
        resource_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ApprovalRequest:
        """Request human approval for an action.

        Args:
            action: Action requiring approval
            reason: Reason for the action
            resource_type: Type of resource (pr, issue, commit, etc.)
            resource_id: ID of the resource
            metadata: Additional metadata

        Returns:
            ApprovalRequest object
        """
        request_id = str(uuid.uuid4())

        request = ApprovalRequest(
            request_id=request_id,
            action=action,
            reason=reason,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata or {},
        )

        # Track pending approval
        self.pending_approvals[request_id] = request
        self.total_requests += 1

        # Log to audit trail
        self.logger.human_approval_requested(
            action=action,
            reason=reason,
            resource_type=resource_type,
            resource_id=resource_id,
        )

        # Notify via callback
        if self.notification_callback:
            try:
                self.notification_callback(request)
            except Exception as e:
                self.logger.error(
                    "Failed to send approval notification",
                    request_id=request_id,
                    error=str(e),
                )

        self.logger.info(
            "Approval request created",
            request_id=request_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
        )

        return request

    def approve(
        self,
        request_id: str,
        approver: str,
        note: Optional[str] = None,
    ) -> ApprovalRequest:
        """Approve a pending request.

        Args:
            request_id: ID of the approval request
            approver: Who approved the request
            note: Optional approval note

        Returns:
            Updated ApprovalRequest

        Raises:
            ValueError: If request not found or not pending
        """
        request = self.pending_approvals.get(request_id)

        if not request:
            raise ValueError(f"Approval request not found: {request_id}")

        if request.status != ApprovalStatus.PENDING:
            raise ValueError(
                f"Request {request_id} is not pending (status: {request.status.value})"
            )

        # Update request
        request.status = ApprovalStatus.APPROVED
        request.responded_at = datetime.now(timezone.utc)
        request.approver = approver
        request.response_note = note

        # Move to history
        self.pending_approvals.pop(request_id)
        self.approval_history.append(request)
        self.total_approved += 1

        # Log to audit trail
        self.logger.audit(
            EventType.HUMAN_APPROVAL_GRANTED,
            f"Approval granted for: {request.action}",
            actor=approver,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
            metadata={
                "request_id": request_id,
                "action": request.action,
                "note": note,
            },
        )

        self.logger.info(
            "Approval request approved",
            request_id=request_id,
            approver=approver,
            action=request.action,
        )

        return request

    def deny(
        self,
        request_id: str,
        approver: str,
        reason: Optional[str] = None,
    ) -> ApprovalRequest:
        """Deny a pending request.

        Args:
            request_id: ID of the approval request
            approver: Who denied the request
            reason: Optional denial reason

        Returns:
            Updated ApprovalRequest

        Raises:
            ValueError: If request not found or not pending
        """
        request = self.pending_approvals.get(request_id)

        if not request:
            raise ValueError(f"Approval request not found: {request_id}")

        if request.status != ApprovalStatus.PENDING:
            raise ValueError(
                f"Request {request_id} is not pending (status: {request.status.value})"
            )

        # Update request
        request.status = ApprovalStatus.DENIED
        request.responded_at = datetime.now(timezone.utc)
        request.approver = approver
        request.response_note = reason

        # Move to history
        self.pending_approvals.pop(request_id)
        self.approval_history.append(request)
        self.total_denied += 1

        # Log to audit trail
        self.logger.audit(
            EventType.HUMAN_APPROVAL_DENIED,
            f"Approval denied for: {request.action}",
            actor=approver,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
            metadata={
                "request_id": request_id,
                "action": request.action,
                "reason": reason,
            },
        )

        self.logger.info(
            "Approval request denied",
            request_id=request_id,
            approver=approver,
            action=request.action,
            reason=reason,
        )

        return request

    def cancel(
        self,
        request_id: str,
        reason: Optional[str] = None,
    ) -> ApprovalRequest:
        """Cancel a pending request.

        Args:
            request_id: ID of the approval request
            reason: Optional cancellation reason

        Returns:
            Updated ApprovalRequest

        Raises:
            ValueError: If request not found or not pending
        """
        request = self.pending_approvals.get(request_id)

        if not request:
            raise ValueError(f"Approval request not found: {request_id}")

        if request.status != ApprovalStatus.PENDING:
            raise ValueError(
                f"Request {request_id} is not pending (status: {request.status.value})"
            )

        # Update request
        request.status = ApprovalStatus.CANCELLED
        request.responded_at = datetime.now(timezone.utc)
        request.response_note = reason

        # Move to history
        self.pending_approvals.pop(request_id)
        self.approval_history.append(request)

        self.logger.info(
            "Approval request cancelled",
            request_id=request_id,
            reason=reason,
        )

        return request

    def expire_old_requests(self) -> List[ApprovalRequest]:
        """Expire old pending approval requests.

        Returns:
            List of expired requests
        """
        now = datetime.now(timezone.utc)
        expired = []

        for request_id, request in list(self.pending_approvals.items()):
            age_seconds = (now - request.requested_at).total_seconds()

            if age_seconds > self.approval_timeout:
                request.status = ApprovalStatus.EXPIRED
                request.responded_at = now

                self.pending_approvals.pop(request_id)
                self.approval_history.append(request)
                self.total_expired += 1

                expired.append(request)

                self.logger.warning(
                    "Approval request expired",
                    request_id=request_id,
                    action=request.action,
                    age_seconds=age_seconds,
                )

        return expired

    def get_pending_requests(self) -> List[ApprovalRequest]:
        """Get all pending approval requests.

        Returns:
            List of pending ApprovalRequest objects
        """
        return list(self.pending_approvals.values())

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get a specific approval request.

        Args:
            request_id: ID of the request

        Returns:
            ApprovalRequest if found, None otherwise
        """
        # Check pending first
        if request_id in self.pending_approvals:
            return self.pending_approvals[request_id]

        # Check history
        for request in self.approval_history:
            if request.request_id == request_id:
                return request

        return None

    def get_statistics(self) -> Dict[str, Any]:
        """Get approval statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "total_requests": self.total_requests,
            "total_approved": self.total_approved,
            "total_denied": self.total_denied,
            "total_expired": self.total_expired,
            "pending_count": len(self.pending_approvals),
            "approval_rate": (
                self.total_approved / self.total_requests
                if self.total_requests > 0
                else 0.0
            ),
        }

    def reset_statistics(self):
        """Reset approval statistics."""
        self.total_requests = 0
        self.total_approved = 0
        self.total_denied = 0
        self.total_expired = 0
