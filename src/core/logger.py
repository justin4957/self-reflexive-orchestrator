"""Logging and audit trail system for the orchestrator."""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from enum import Enum

import structlog
from structlog.processors import JSONRenderer
from structlog.stdlib import BoundLogger


class EventType(Enum):
    """Types of events to audit."""

    # Issue cycle events
    ISSUE_CLAIMED = "issue_claimed"
    ISSUE_ANALYZED = "issue_analyzed"
    ISSUE_IMPLEMENTATION_STARTED = "issue_implementation_started"
    ISSUE_IMPLEMENTATION_COMPLETED = "issue_implementation_completed"
    ISSUE_IMPLEMENTATION_FAILED = "issue_implementation_failed"

    # PR cycle events
    PR_CREATED = "pr_created"
    PR_UPDATED = "pr_updated"
    PR_CI_PASSED = "pr_ci_passed"
    PR_CI_FAILED = "pr_ci_failed"
    PR_REVIEWED = "pr_reviewed"
    PR_REVIEW_FAILED = "pr_review_failed"
    PR_REVIEW_REQUESTED = "pr_review_requested"
    PR_REVIEW_COMPLETED = "pr_review_completed"
    PR_MERGED = "pr_merged"
    PR_CLOSED = "pr_closed"

    # Code review events
    CODE_REVIEW_STARTED = "code_review_started"
    CODE_REVIEW_APPROVED = "code_review_approved"
    CODE_REVIEW_REJECTED = "code_review_rejected"
    CODE_REVIEW_CHANGES_REQUESTED = "code_review_changes_requested"

    # Roadmap events
    ROADMAP_GENERATED = "roadmap_generated"
    ROADMAP_VALIDATED = "roadmap_validated"
    ROADMAP_ISSUES_CREATED = "roadmap_issues_created"

    # Code execution events
    BRANCH_CREATED = "branch_created"
    CODE_COMMITTED = "code_committed"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"

    # Safety events
    HUMAN_APPROVAL_REQUESTED = "human_approval_requested"
    HUMAN_APPROVAL_GRANTED = "human_approval_granted"
    HUMAN_APPROVAL_DENIED = "human_approval_denied"
    ROLLBACK_TRIGGERED = "rollback_triggered"
    SAFETY_GUARD_TRIGGERED = "safety_guard_triggered"

    # System events
    ORCHESTRATOR_STARTED = "orchestrator_started"
    ORCHESTRATOR_STOPPED = "orchestrator_stopped"
    ERROR_OCCURRED = "error_occurred"
    CONFIG_LOADED = "config_loaded"
    STATE_CHANGED = "state_changed"


class AuditLogger:
    """Structured logger for audit trails and system events."""

    def __init__(
        self,
        log_level: str = "INFO",
        log_file: Optional[str] = None,
        audit_file: Optional[str] = None,
        structured: bool = True,
    ):
        """Initialize audit logger.

        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
            log_file: Path to main log file
            audit_file: Path to audit log file
            structured: Whether to use structured JSON logging
        """
        self.log_level = getattr(logging, log_level.upper())
        self.log_file = log_file
        self.audit_file = audit_file
        self.structured = structured

        # Create log directories if needed
        if log_file:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        if audit_file:
            Path(audit_file).parent.mkdir(parents=True, exist_ok=True)

        # Set up structlog
        self._setup_structlog()

        # Create loggers
        self.logger: BoundLogger = structlog.get_logger("orchestrator")
        self.audit_logger: BoundLogger = structlog.get_logger("audit")

    def _setup_structlog(self):
        """Configure structlog for structured logging."""
        processors = [
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
        ]

        if self.structured:
            processors.append(JSONRenderer())
        else:
            processors.append(structlog.dev.ConsoleRenderer())

        structlog.configure(
            processors=processors,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        # Configure standard logging
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=self.log_level,
        )

        # Add file handler if specified
        if self.log_file:
            file_handler = logging.FileHandler(self.log_file)
            file_handler.setLevel(self.log_level)
            logging.root.addHandler(file_handler)

        # Add audit file handler if specified
        if self.audit_file:
            audit_handler = logging.FileHandler(self.audit_file)
            audit_handler.setLevel(logging.INFO)
            audit_handler.setFormatter(logging.Formatter("%(message)s"))

            # Create separate logger for audit
            audit_log = logging.getLogger("audit")
            audit_log.addHandler(audit_handler)
            audit_log.setLevel(logging.INFO)

    def log(
        self,
        level: str,
        message: str,
        **kwargs: Any,
    ):
        """Log a message with structured data.

        Args:
            level: Log level (debug, info, warning, error)
            message: Log message
            **kwargs: Additional structured data
        """
        log_func = getattr(self.logger, level.lower())
        log_func(message, **kwargs)

    def audit(
        self,
        event_type: EventType,
        message: str,
        actor: str = "orchestrator",
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ):
        """Create an audit log entry.

        Args:
            event_type: Type of event being audited
            message: Human-readable description
            actor: Who/what performed the action
            resource_type: Type of resource affected (issue, pr, commit, etc.)
            resource_id: ID of the resource
            metadata: Additional metadata
            **kwargs: Additional fields
        """
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type.value,
            "message": message,
            "actor": actor,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "metadata": metadata or {},
            **kwargs,
        }

        self.audit_logger.info("audit_event", **audit_entry)

        # Also write to separate audit file if configured
        if self.audit_file:
            with open(self.audit_file, "a") as f:
                f.write(json.dumps(audit_entry) + "\n")

    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self.log("debug", message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log info message."""
        self.log("info", message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self.log("warning", message, **kwargs)

    def error(self, message: str, **kwargs):
        """Log error message."""
        self.log("error", message, **kwargs)

        # Also create audit entry for errors
        self.audit(
            EventType.ERROR_OCCURRED,
            message,
            metadata=kwargs,
        )

    def issue_claimed(
        self, issue_number: int, issue_title: str, complexity: Optional[int] = None
    ):
        """Audit: Issue claimed for processing."""
        self.audit(
            EventType.ISSUE_CLAIMED,
            f"Claimed issue #{issue_number}: {issue_title}",
            resource_type="issue",
            resource_id=str(issue_number),
            metadata={"title": issue_title, "complexity": complexity},
        )

    def pr_created(
        self,
        pr_number: int,
        pr_title: str,
        branch: str,
        issue_number: Optional[int] = None,
    ):
        """Audit: Pull request created."""
        self.audit(
            EventType.PR_CREATED,
            f"Created PR #{pr_number}: {pr_title}",
            resource_type="pr",
            resource_id=str(pr_number),
            metadata={
                "title": pr_title,
                "branch": branch,
                "linked_issue": issue_number,
            },
        )

    def pr_merged(self, pr_number: int, pr_title: str, merge_commit: str):
        """Audit: Pull request merged."""
        self.audit(
            EventType.PR_MERGED,
            f"Merged PR #{pr_number}: {pr_title}",
            resource_type="pr",
            resource_id=str(pr_number),
            metadata={
                "title": pr_title,
                "merge_commit": merge_commit,
            },
        )

    def code_review_completed(
        self,
        pr_number: int,
        approved: bool,
        reviewer: str,
        comments: Optional[str] = None,
    ):
        """Audit: Code review completed."""
        event = (
            EventType.CODE_REVIEW_APPROVED
            if approved
            else EventType.CODE_REVIEW_REJECTED
        )
        self.audit(
            event,
            f"Code review {'approved' if approved else 'rejected'} for PR #{pr_number}",
            resource_type="pr",
            resource_id=str(pr_number),
            metadata={
                "reviewer": reviewer,
                "comments": comments,
            },
        )

    def human_approval_requested(
        self,
        action: str,
        reason: str,
        resource_type: str,
        resource_id: str,
    ):
        """Audit: Human approval requested."""
        self.audit(
            EventType.HUMAN_APPROVAL_REQUESTED,
            f"Human approval requested for: {action}",
            resource_type=resource_type,
            resource_id=resource_id,
            metadata={
                "action": action,
                "reason": reason,
            },
        )

    def safety_guard_triggered(
        self,
        guard_name: str,
        reason: str,
        action_blocked: str,
    ):
        """Audit: Safety guard prevented an action."""
        self.audit(
            EventType.SAFETY_GUARD_TRIGGERED,
            f"Safety guard '{guard_name}' triggered: {reason}",
            metadata={
                "guard": guard_name,
                "reason": reason,
                "blocked_action": action_blocked,
            },
        )

    def state_changed(
        self, from_state: str, to_state: str, reason: Optional[str] = None
    ):
        """Audit: Orchestrator state changed."""
        self.audit(
            EventType.STATE_CHANGED,
            f"State changed from {from_state} to {to_state}",
            metadata={
                "from_state": from_state,
                "to_state": to_state,
                "reason": reason,
            },
        )


# Global logger instance
_logger: Optional[AuditLogger] = None


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    audit_file: Optional[str] = None,
    structured: bool = True,
) -> AuditLogger:
    """Set up global logging.

    Args:
        log_level: Logging level
        log_file: Path to log file
        audit_file: Path to audit file
        structured: Use structured JSON logging

    Returns:
        Configured AuditLogger instance
    """
    global _logger
    _logger = AuditLogger(
        log_level=log_level,
        log_file=log_file,
        audit_file=audit_file,
        structured=structured,
    )
    return _logger


def get_logger() -> AuditLogger:
    """Get global logger instance.

    Returns:
        AuditLogger instance

    Raises:
        RuntimeError: If logging not yet set up
    """
    if _logger is None:
        raise RuntimeError("Logging not set up. Call setup_logging() first.")
    return _logger
