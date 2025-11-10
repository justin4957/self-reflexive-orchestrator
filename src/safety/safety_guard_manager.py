"""Safety Guard Manager - coordinates all safety mechanisms."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.logger import AuditLogger
from ..integrations.multi_agent_coder_client import MultiAgentCoderClient
from .breaking_change_detector import BreakingChangeAnalysis, BreakingChangeDetector
from .guards import GuardDecision, Operation, OperationGuard, RiskLevel
from .multi_agent_risk_assessor import MultiAgentRiskAssessor, RiskAssessment


@dataclass
class SafetyCheckResult:
    """Result of comprehensive safety check."""

    allowed: bool
    requires_approval: bool
    risk_level: RiskLevel
    operations_detected: List[Operation]
    risk_assessments: List[RiskAssessment] = field(default_factory=list)
    breaking_change_analysis: Optional[BreakingChangeAnalysis] = None
    guard_decision: Optional[GuardDecision] = None
    summary: str = ""
    blocking_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "allowed": self.allowed,
            "requires_approval": self.requires_approval,
            "risk_level": self.risk_level.value,
            "operations_detected": [op.to_dict() for op in self.operations_detected],
            "risk_assessments": [ra.to_dict() for ra in self.risk_assessments],
            "breaking_change_analysis": (
                self.breaking_change_analysis.to_dict()
                if self.breaking_change_analysis
                else None
            ),
            "guard_decision": (
                self.guard_decision.to_dict() if self.guard_decision else None
            ),
            "summary": self.summary,
            "blocking_reasons": self.blocking_reasons,
        }


class SafetyGuardManager:
    """Coordinates all safety guards and enforcement.

    Decision Matrix:
    - CRITICAL risk: Block immediately
    - HIGH risk (≥50% consensus): Require human approval
    - MEDIUM risk (≥66% consensus): Require review
    - LOW risk (≥75% consensus): Proceed with monitoring
    """

    def __init__(
        self,
        multi_agent_client: MultiAgentCoderClient,
        logger: AuditLogger,
        enable_multi_agent_assessment: bool = True,
        enable_breaking_change_detection: bool = True,
    ):
        """Initialize safety guard manager.

        Args:
            multi_agent_client: Multi-agent-coder client
            logger: Audit logger
            enable_multi_agent_assessment: Enable AI risk assessment
            enable_breaking_change_detection: Enable breaking change detection
        """
        self.logger = logger
        self.enable_multi_agent = enable_multi_agent_assessment
        self.enable_breaking_change = enable_breaking_change_detection

        # Initialize components
        self.operation_guard = OperationGuard(logger=logger)

        if enable_multi_agent_assessment:
            self.risk_assessor = MultiAgentRiskAssessor(
                multi_agent_client=multi_agent_client,
                logger=logger,
            )

        if enable_breaking_change_detection:
            self.breaking_change_detector = BreakingChangeDetector(
                multi_agent_client=multi_agent_client,
                logger=logger,
            )

        self.logger.info(
            "safety_guard_manager_initialized",
            multi_agent_enabled=enable_multi_agent_assessment,
            breaking_change_enabled=enable_breaking_change_detection,
        )

    def check_operation_safety(
        self,
        files_changed: List[str],
        files_deleted: List[str] = None,
        diff: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> SafetyCheckResult:
        """Perform comprehensive safety check on operation.

        Args:
            files_changed: Files being changed
            files_deleted: Files being deleted
            diff: Git diff of changes
            context: Additional context

        Returns:
            SafetyCheckResult with decision and rationale
        """
        self.logger.info(
            "safety_check_started",
            files_changed=len(files_changed),
            files_deleted=len(files_deleted or []),
        )

        # Step 1: Detect operations
        operations = self.operation_guard.detect_operations(
            files_changed=files_changed,
            files_deleted=files_deleted or [],
            diff=diff,
            context=context,
        )

        if not operations:
            # No concerning operations detected
            return SafetyCheckResult(
                allowed=True,
                requires_approval=False,
                risk_level=RiskLevel.LOW,
                operations_detected=[],
                summary="No safety concerns detected",
            )

        # Step 2: Assess risk with multi-agent (if enabled)
        risk_assessments = []
        highest_risk = RiskLevel.LOW

        if self.enable_multi_agent:
            for operation in operations:
                assessment = self.risk_assessor.assess_operation(operation)
                risk_assessments.append(assessment)

                # Track highest risk
                if self._risk_level_value(
                    assessment.risk_level
                ) > self._risk_level_value(highest_risk):
                    highest_risk = assessment.risk_level

        # Step 3: Check for breaking changes (if enabled)
        breaking_analysis = None
        if self.enable_breaking_change and diff:
            breaking_analysis = self.breaking_change_detector.detect_breaking_changes(
                diff=diff,
                files_changed=files_changed,
            )

            # Elevate risk if critical breaking changes
            if breaking_analysis.overall_severity == "CRITICAL":
                highest_risk = RiskLevel.CRITICAL

        # Step 4: Make decision based on risk level
        decision = self._make_decision(
            highest_risk, risk_assessments, breaking_analysis
        )

        result = SafetyCheckResult(
            allowed=decision.allowed,
            requires_approval=decision.requires_approval,
            risk_level=highest_risk,
            operations_detected=operations,
            risk_assessments=risk_assessments,
            breaking_change_analysis=breaking_analysis,
            guard_decision=decision,
            summary=decision.rationale,
            blocking_reasons=decision.blocking_reasons,
        )

        self.logger.info(
            "safety_check_completed",
            allowed=result.allowed,
            requires_approval=result.requires_approval,
            risk_level=highest_risk.value,
            operations_count=len(operations),
        )

        return result

    def _make_decision(
        self,
        risk_level: RiskLevel,
        assessments: List[RiskAssessment],
        breaking_analysis: Optional[BreakingChangeAnalysis],
    ) -> GuardDecision:
        """Make enforcement decision based on risk level.

        Args:
            risk_level: Overall risk level
            assessments: Risk assessments
            breaking_analysis: Breaking change analysis

        Returns:
            GuardDecision
        """
        blocking_reasons = []
        warnings = []
        recommendations = []

        # Build rationale
        rationale_parts = [f"Overall Risk: {risk_level.value.upper()}"]

        if assessments:
            rationale_parts.append(
                f"\n{len(assessments)} operation(s) assessed by multi-agent system"
            )

        if breaking_analysis:
            rationale_parts.append(
                f"\nBreaking changes: {breaking_analysis.overall_severity}"
            )

        # Decision matrix
        if risk_level == RiskLevel.CRITICAL:
            allowed = False
            requires_approval = False  # Too risky even with approval
            blocking_reasons.append(
                "CRITICAL risk level - operation blocked for safety"
            )

            rationale_parts.append("\n❌ Operation BLOCKED - Critical risk detected")

        elif risk_level == RiskLevel.HIGH:
            allowed = False
            requires_approval = True
            warnings.append("HIGH risk level - human approval required")

            rationale_parts.append("\n⚠️  Operation requires HUMAN APPROVAL")

        elif risk_level == RiskLevel.MEDIUM:
            allowed = True
            requires_approval = True
            warnings.append("MEDIUM risk level - review recommended")
            recommendations.append("Proceed with caution and enhanced monitoring")

            rationale_parts.append("\n⚠️  Operation allowed with REVIEW")

        else:  # LOW
            allowed = True
            requires_approval = False
            recommendations.append("Proceed with standard monitoring")

            rationale_parts.append("\n✓ Operation allowed - low risk")

        rationale = "\n".join(rationale_parts)

        # Create dummy operation for decision (use first if available)
        operation = (
            assessments[0].operation
            if assessments
            else Operation(
                operation_type=(
                    assessments[0].operation.operation_type if assessments else None
                ),
                description="Multiple operations",
            )
        )

        return GuardDecision(
            allowed=allowed,
            risk_level=risk_level,
            operation=operation,
            rationale=rationale,
            requires_approval=requires_approval,
            blocking_reasons=blocking_reasons,
            warnings=warnings,
            recommendations=recommendations,
        )

    def _risk_level_value(self, risk_level: RiskLevel) -> int:
        """Get numeric value for risk level comparison."""
        hierarchy = {
            RiskLevel.LOW: 1,
            RiskLevel.MEDIUM: 2,
            RiskLevel.HIGH: 3,
            RiskLevel.CRITICAL: 4,
        }
        return hierarchy.get(risk_level, 0)
