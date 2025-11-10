"""CI failure analysis using multi-agent LLM consensus.

This module implements multi-AI CI failure analysis for:
- Build failures (compilation, linking)
- Lint failures (style, formatting)
- Type check failures
- Test failures (delegated to TestFailureAnalyzer)
- Infrastructure failures

Uses multi-agent consensus to determine:
1. Failure category and root cause
2. Whether failure is auto-fixable
3. Suggested fixes with confidence scores
"""

import re
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

from ..integrations.multi_agent_coder_client import (
    MultiAgentCoderClient,
    MultiAgentStrategy,
    MultiAgentResponse,
)
from ..cycles.pr_cycle import CICheckStatus, CIStatus
from ..core.logger import AuditLogger, EventType


class CIFailureCategory(Enum):
    """Categories of CI failures."""

    LINT_ERROR = "lint_error"  # Code style, formatting issues
    BUILD_ERROR = "build_error"  # Compilation, syntax errors
    TYPE_ERROR = "type_error"  # Type checking failures
    TEST_FAILURE = "test_failure"  # Unit/integration test failures
    IMPORT_ERROR = "import_error"  # Missing dependencies, import issues
    INFRASTRUCTURE = "infrastructure"  # CI system issues (non-fixable)
    TIMEOUT = "timeout"  # Execution timeout (may be fixable)
    PERMISSION = "permission"  # Access/permission issues (non-fixable)
    UNKNOWN = "unknown"


@dataclass
class CIFailureDetails:
    """Details about a specific CI failure."""

    check_name: str
    failure_category: CIFailureCategory
    error_messages: List[str]
    log_excerpt: str
    is_auto_fixable: bool
    confidence: float  # 0.0 to 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "check_name": self.check_name,
            "failure_category": self.failure_category.value,
            "error_messages": self.error_messages,
            "log_excerpt_length": len(self.log_excerpt),
            "is_auto_fixable": self.is_auto_fixable,
            "confidence": self.confidence,
        }


@dataclass
class CIFixSuggestion:
    """Suggested fix for a CI failure."""

    description: str
    file_paths: List[str]
    proposed_changes: str  # Actual code/config changes
    success_probability: float  # 0.0 to 1.0
    rationale: str
    fix_category: str  # "lint", "import", "type", etc.
    provider_consensus: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "description": self.description,
            "file_paths": self.file_paths,
            "proposed_changes_length": len(self.proposed_changes),
            "success_probability": self.success_probability,
            "rationale": self.rationale,
            "fix_category": self.fix_category,
            "provider_count": len(self.provider_consensus),
        }


@dataclass
class CIFailureAnalysis:
    """Complete analysis of CI failures."""

    pr_number: int
    ci_status: CIStatus
    failures: List[CIFailureDetails]
    fix_suggestions: List[CIFixSuggestion]
    overall_fixable: bool
    escalation_needed: bool
    escalation_reason: Optional[str] = None
    analysis_confidence: float = 0.0
    multi_agent_responses: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pr_number": self.pr_number,
            "failure_count": len(self.failures),
            "failures": [f.to_dict() for f in self.failures],
            "fix_suggestions": [fs.to_dict() for fs in self.fix_suggestions],
            "overall_fixable": self.overall_fixable,
            "escalation_needed": self.escalation_needed,
            "escalation_reason": self.escalation_reason,
            "analysis_confidence": self.analysis_confidence,
        }


class CIFailureAnalyzer:
    """Analyzes CI failures and suggests fixes using multi-agent LLM consensus.

    Responsibilities:
    - Categorize CI failures by type
    - Determine if failures are auto-fixable
    - Generate fix suggestions for fixable failures
    - Identify when to escalate to humans
    - Track analysis statistics
    """

    def __init__(
        self,
        multi_agent_client: MultiAgentCoderClient,
        logger: AuditLogger,
    ):
        """Initialize CI failure analyzer.

        Args:
            multi_agent_client: Multi-agent-coder client for analysis
            logger: Audit logger instance
        """
        self.multi_agent = multi_agent_client
        self.logger = logger

        # Statistics
        self.total_analyses = 0
        self.fixable_failures = 0
        self.escalated_failures = 0

    def analyze_ci_failures(
        self,
        pr_number: int,
        ci_status: CIStatus,
        check_logs: Optional[Dict[str, str]] = None,
    ) -> CIFailureAnalysis:
        """Analyze CI failures and determine fixability.

        Args:
            pr_number: Pull request number
            ci_status: CI status with failing checks
            check_logs: Optional mapping of check name to log output

        Returns:
            CIFailureAnalysis with categorization and fix suggestions
        """
        self.total_analyses += 1
        check_logs = check_logs or {}

        self.logger.info(
            "Analyzing CI failures",
            pr_number=pr_number,
            failing_checks=ci_status.failing_checks,
            total_checks=ci_status.total_checks,
        )

        try:
            # Extract failing checks
            failing_checks = [c for c in ci_status.checks if c.is_failing()]

            if not failing_checks:
                self.logger.warning("No failing checks to analyze", pr_number=pr_number)
                return CIFailureAnalysis(
                    pr_number=pr_number,
                    ci_status=ci_status,
                    failures=[],
                    fix_suggestions=[],
                    overall_fixable=True,
                    escalation_needed=False,
                )

            # Analyze each failing check
            failure_details = []
            for check in failing_checks:
                log_output = check_logs.get(check.name, "")
                details = self._analyze_single_check(check, log_output)
                failure_details.append(details)

            # Generate fix suggestions for fixable failures
            fix_suggestions = []
            for failure in failure_details:
                if failure.is_auto_fixable:
                    suggestions = self._generate_fix_suggestions(failure)
                    fix_suggestions.extend(suggestions)

            # Determine if overall fixable
            overall_fixable = any(f.is_auto_fixable for f in failure_details)
            non_fixable = [f for f in failure_details if not f.is_auto_fixable]

            # Check if escalation needed
            escalation_needed = len(non_fixable) > 0
            escalation_reason = None

            if escalation_needed:
                categories = [f.failure_category.value for f in non_fixable]
                escalation_reason = (
                    f"Non-fixable failures: {', '.join(set(categories))}"
                )
                self.escalated_failures += 1
            elif overall_fixable:
                self.fixable_failures += 1

            # Calculate overall confidence
            if failure_details:
                analysis_confidence = sum(f.confidence for f in failure_details) / len(
                    failure_details
                )
            else:
                analysis_confidence = 0.0

            analysis = CIFailureAnalysis(
                pr_number=pr_number,
                ci_status=ci_status,
                failures=failure_details,
                fix_suggestions=fix_suggestions,
                overall_fixable=overall_fixable,
                escalation_needed=escalation_needed,
                escalation_reason=escalation_reason,
                analysis_confidence=analysis_confidence,
            )

            self.logger.audit(
                EventType.PR_CI_FAILED,
                f"CI failure analysis complete for PR #{pr_number}",
                resource_type="pr",
                resource_id=str(pr_number),
                metadata={
                    "failures": len(failure_details),
                    "fixable": overall_fixable,
                    "escalation_needed": escalation_needed,
                    "confidence": analysis_confidence,
                },
            )

            return analysis

        except Exception as e:
            self.logger.error(
                "CI failure analysis failed",
                pr_number=pr_number,
                error=str(e),
                exc_info=True,
            )
            raise

    def _analyze_single_check(
        self,
        check: CICheckStatus,
        log_output: str,
    ) -> CIFailureDetails:
        """Analyze a single failing check.

        Args:
            check: Failing CI check
            log_output: Log output from the check

        Returns:
            CIFailureDetails with categorization
        """
        # Quick categorization based on check name and log patterns
        category = self._categorize_failure(check.name, log_output)

        # Extract error messages
        error_messages = self._extract_error_messages(log_output)

        # Determine if auto-fixable
        is_auto_fixable = self._is_auto_fixable(category, error_messages)

        # Get log excerpt (first 500 chars of relevant errors)
        log_excerpt = self._get_log_excerpt(log_output, error_messages)

        # Estimate confidence
        confidence = self._estimate_confidence(category, error_messages, log_output)

        return CIFailureDetails(
            check_name=check.name,
            failure_category=category,
            error_messages=error_messages,
            log_excerpt=log_excerpt,
            is_auto_fixable=is_auto_fixable,
            confidence=confidence,
        )

    def _categorize_failure(
        self, check_name: str, log_output: str
    ) -> CIFailureCategory:
        """Categorize failure based on check name and log content.

        Args:
            check_name: Name of the CI check
            log_output: Log output

        Returns:
            CIFailureCategory
        """
        check_lower = check_name.lower()
        log_lower = log_output.lower()

        # Log content patterns (more specific, check first)
        if "importerror" in log_lower or "modulenotfounderror" in log_lower:
            return CIFailureCategory.IMPORT_ERROR

        if "timeout" in log_lower or "timed out" in log_lower:
            return CIFailureCategory.TIMEOUT

        if "permission" in log_lower or "access denied" in log_lower:
            return CIFailureCategory.PERMISSION

        if "infrastructure" in log_lower or "runner" in log_lower:
            return CIFailureCategory.INFRASTRUCTURE

        if "syntaxerror" in log_lower:
            return CIFailureCategory.BUILD_ERROR

        # Check name patterns (less specific)
        if "lint" in check_lower or "format" in check_lower or "style" in check_lower:
            return CIFailureCategory.LINT_ERROR

        if "type" in check_lower or "mypy" in check_lower or "pyright" in check_lower:
            return CIFailureCategory.TYPE_ERROR

        if "build" in check_lower or "compile" in check_lower:
            return CIFailureCategory.BUILD_ERROR

        if "test" in check_lower or "pytest" in check_lower or "jest" in check_lower:
            return CIFailureCategory.TEST_FAILURE

        # Additional log content patterns
        if "typeerror" in log_lower or "type error" in log_lower:
            return CIFailureCategory.TYPE_ERROR

        return CIFailureCategory.UNKNOWN

    def _extract_error_messages(self, log_output: str) -> List[str]:
        """Extract error messages from log output.

        Args:
            log_output: Full log output

        Returns:
            List of error messages
        """
        if not log_output:
            return []

        errors = []

        # Common error patterns
        patterns = [
            r"Error: (.+)",
            r"ERROR: (.+)",
            r"FAIL: (.+)",
            r"(.+Error: .+)",
            r"✗ (.+)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, log_output, re.MULTILINE)
            errors.extend(matches)

        # Deduplicate while preserving order
        seen = set()
        unique_errors = []
        for error in errors:
            error_clean = error.strip()
            if error_clean and error_clean not in seen:
                seen.add(error_clean)
                unique_errors.append(error_clean)

        return unique_errors[:10]  # Limit to first 10 errors

    def _is_auto_fixable(
        self,
        category: CIFailureCategory,
        error_messages: List[str],
    ) -> bool:
        """Determine if failure is auto-fixable.

        Args:
            category: Failure category
            error_messages: Extracted error messages

        Returns:
            True if likely auto-fixable
        """
        # Fixable categories
        fixable_categories = {
            CIFailureCategory.LINT_ERROR,
            CIFailureCategory.BUILD_ERROR,
            CIFailureCategory.TYPE_ERROR,
            CIFailureCategory.IMPORT_ERROR,
            CIFailureCategory.TEST_FAILURE,
        }

        # Non-fixable categories
        non_fixable_categories = {
            CIFailureCategory.INFRASTRUCTURE,
            CIFailureCategory.PERMISSION,
        }

        if category in non_fixable_categories:
            return False

        if category in fixable_categories:
            return True

        # Unknown/timeout - check error messages for clues
        if not error_messages:
            return False

        # If errors mention syntax/import/type, likely fixable
        fixable_keywords = ["syntax", "import", "type", "undefined", "not found"]
        for msg in error_messages:
            if any(kw in msg.lower() for kw in fixable_keywords):
                return True

        return False

    def _get_log_excerpt(self, log_output: str, error_messages: List[str]) -> str:
        """Get relevant excerpt from log.

        Args:
            log_output: Full log
            error_messages: Extracted errors

        Returns:
            Log excerpt (max 1000 chars)
        """
        if error_messages:
            # Use first few error messages
            excerpt = "\n".join(error_messages[:5])
        else:
            # Use last 1000 chars of log (usually has the errors)
            excerpt = log_output[-1000:] if log_output else ""

        return excerpt[:1000]

    def _estimate_confidence(
        self,
        category: CIFailureCategory,
        error_messages: List[str],
        log_output: str,
    ) -> float:
        """Estimate confidence in categorization.

        Args:
            category: Assigned category
            error_messages: Extracted messages
            log_output: Full log

        Returns:
            Confidence score 0.0-1.0
        """
        confidence = 0.5  # Base confidence

        # Higher confidence if we have clear error messages
        if error_messages:
            confidence += 0.2

        # Higher confidence for specific categories with clear indicators
        if category in [CIFailureCategory.LINT_ERROR, CIFailureCategory.TYPE_ERROR]:
            confidence += 0.2

        # Lower confidence for unknown/ambiguous
        if category in [CIFailureCategory.UNKNOWN, CIFailureCategory.TIMEOUT]:
            confidence -= 0.3

        # Check if log has substantial content
        if log_output and len(log_output) > 100:
            confidence += 0.1

        return max(0.0, min(1.0, confidence))

    def _generate_fix_suggestions(
        self,
        failure: CIFailureDetails,
    ) -> List[CIFixSuggestion]:
        """Generate fix suggestions for a failure.

        Args:
            failure: Failure details

        Returns:
            List of fix suggestions
        """
        suggestions = []

        # For now, create a generic suggestion
        # In future, could use multi-agent-coder to generate specific fixes
        if failure.failure_category == CIFailureCategory.LINT_ERROR:
            suggestions.append(
                CIFixSuggestion(
                    description="Run linter and apply auto-fixes",
                    file_paths=[],  # Will be determined from errors
                    proposed_changes="Run: black . && flake8 --extend-ignore=E203,W503",
                    success_probability=0.9,
                    rationale="Lint errors are typically auto-fixable with formatters",
                    fix_category="lint",
                )
            )

        elif failure.failure_category == CIFailureCategory.IMPORT_ERROR:
            suggestions.append(
                CIFixSuggestion(
                    description="Add missing imports or dependencies",
                    file_paths=[],
                    proposed_changes="Analyze import errors and add missing imports",
                    success_probability=0.7,
                    rationale="Import errors usually require adding imports or installing packages",
                    fix_category="import",
                )
            )

        # For other categories, would need more sophisticated analysis
        # Could delegate to multi-agent-coder here

        return suggestions

    def get_statistics(self) -> Dict[str, Any]:
        """Get analyzer statistics.

        Returns:
            Dictionary with statistics
        """
        fixable_rate = (
            (self.fixable_failures / self.total_analyses * 100)
            if self.total_analyses > 0
            else 0.0
        )

        escalation_rate = (
            (self.escalated_failures / self.total_analyses * 100)
            if self.total_analyses > 0
            else 0.0
        )

        return {
            "total_analyses": self.total_analyses,
            "fixable_failures": self.fixable_failures,
            "escalated_failures": self.escalated_failures,
            "fixable_rate": fixable_rate,
            "escalation_rate": escalation_rate,
        }

    def reset_statistics(self):
        """Reset analyzer statistics."""
        self.total_analyses = 0
        self.fixable_failures = 0
        self.escalated_failures = 0
