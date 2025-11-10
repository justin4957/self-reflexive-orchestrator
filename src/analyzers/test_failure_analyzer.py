"""Test failure analysis using multi-agent LLM consensus.

This module implements multi-AI test failure analysis:
1. Parallel analysis - Multiple AIs independently analyze failures
2. Dialectical synthesis - Thesis/Antithesis/Synthesis for best fix
3. Fix confidence scoring - Estimate fix success probability
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.logger import AuditLogger, EventType
from ..integrations.multi_agent_coder_client import (
    MultiAgentCoderClient,
    MultiAgentResponse,
    MultiAgentStrategy,
)
from ..integrations.test_runner import TestFailure, TestFramework, TestResult


class FailureCategory(Enum):
    """Categories of test failures."""

    ASSERTION_ERROR = "assertion_error"
    IMPORT_ERROR = "import_error"
    SYNTAX_ERROR = "syntax_error"
    TYPE_ERROR = "type_error"
    ATTRIBUTE_ERROR = "attribute_error"
    RUNTIME_ERROR = "runtime_error"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class RootCause:
    """Identified root cause of a test failure."""

    description: str
    category: FailureCategory
    confidence: float  # 0.0 to 1.0
    affected_files: List[str] = field(default_factory=list)
    related_failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "description": self.description,
            "category": self.category.value,
            "confidence": self.confidence,
            "affected_files": self.affected_files,
            "related_failures": self.related_failures,
        }


@dataclass
class FixSuggestion:
    """Suggested fix for a test failure."""

    description: str
    file_path: str
    proposed_changes: str
    success_probability: float  # 0.0 to 1.0
    rationale: str
    provider_consensus: Dict[str, str] = field(default_factory=dict)
    alternative_approaches: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "description": self.description,
            "file_path": self.file_path,
            "proposed_changes": self.proposed_changes,
            "success_probability": self.success_probability,
            "rationale": self.rationale,
            "provider_consensus": self.provider_consensus,
            "alternative_approaches": self.alternative_approaches,
        }


@dataclass
class FailureAnalysis:
    """Complete analysis of a test failure."""

    test_failure: TestFailure
    root_causes: List[RootCause]
    fix_suggestions: List[FixSuggestion]
    is_related_to_changes: bool
    multi_agent_responses: Dict[str, str] = field(default_factory=dict)
    analysis_confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "test_failure": self.test_failure.to_dict(),
            "root_causes": [rc.to_dict() for rc in self.root_causes],
            "fix_suggestions": [fs.to_dict() for fs in self.fix_suggestions],
            "is_related_to_changes": self.is_related_to_changes,
            "analysis_confidence": self.analysis_confidence,
            "provider_count": len(self.multi_agent_responses),
        }


class TestFailureAnalyzer:
    """Analyzes test failures using multi-agent LLM consensus.

    Workflow:
    1. Parallel Analysis (ALL strategy): Multiple AIs analyze failures
    2. Synthesis (DIALECTICAL strategy): Build consensus on fixes
    3. Confidence Scoring: Estimate fix success probability
    """

    def __init__(
        self,
        multi_agent_client: MultiAgentCoderClient,
        logger: AuditLogger,
        repo_path: Path,
        min_confidence_threshold: float = 0.6,
    ):
        """Initialize test failure analyzer.

        Args:
            multi_agent_client: Client for multi-agent-coder integration
            logger: Audit logger instance
            repo_path: Path to repository root
            min_confidence_threshold: Minimum confidence to suggest auto-fix
        """
        self.multi_agent_client = multi_agent_client
        self.logger = logger
        self.repo_path = Path(repo_path)
        self.min_confidence_threshold = min_confidence_threshold

        # Statistics
        self.total_analyses = 0
        self.successful_analyses = 0
        self.failed_analyses = 0

    def analyze_test_failures(
        self,
        test_result: TestResult,
        changed_files: Optional[List[str]] = None,
        codebase_context: Optional[str] = None,
    ) -> List[FailureAnalysis]:
        """Analyze all test failures in a test result.

        Args:
            test_result: Test result with failures to analyze
            changed_files: List of recently changed files
            codebase_context: Additional context about the codebase

        Returns:
            List of FailureAnalysis for each failure
        """
        if not test_result.failures:
            self.logger.debug("No test failures to analyze")
            return []

        self.logger.info(
            "Analyzing test failures",
            failure_count=len(test_result.failures),
            framework=test_result.framework.value,
        )

        analyses = []
        for failure in test_result.failures:
            try:
                analysis = self.analyze_single_failure(
                    failure=failure,
                    framework=test_result.framework,
                    changed_files=changed_files,
                    codebase_context=codebase_context,
                )
                analyses.append(analysis)
                self.successful_analyses += 1

            except Exception as e:
                self.logger.error(
                    "Failed to analyze test failure",
                    test_name=failure.test_name,
                    error=str(e),
                    exc_info=True,
                )
                self.failed_analyses += 1

            self.total_analyses += 1

        return analyses

    def analyze_single_failure(
        self,
        failure: TestFailure,
        framework: TestFramework,
        changed_files: Optional[List[str]] = None,
        codebase_context: Optional[str] = None,
    ) -> FailureAnalysis:
        """Analyze a single test failure using multi-agent consensus.

        Args:
            failure: Test failure to analyze
            framework: Test framework used
            changed_files: List of recently changed files
            codebase_context: Additional context about the codebase

        Returns:
            FailureAnalysis with root causes and fix suggestions
        """
        self.logger.debug(
            "Analyzing single test failure",
            test_name=failure.test_name,
            test_file=failure.test_file,
        )

        # Step 1: Parallel analysis - Get multiple perspectives
        parallel_analysis = self._run_parallel_analysis(
            failure=failure,
            framework=framework,
            changed_files=changed_files,
            codebase_context=codebase_context,
        )

        # Step 2: Extract root causes from multi-agent responses
        root_causes = self._extract_root_causes(
            failure=failure,
            multi_agent_response=parallel_analysis,
        )

        # Step 3: Dialectical synthesis for fix suggestions
        fix_suggestions = self._synthesize_fix_suggestions(
            failure=failure,
            root_causes=root_causes,
            parallel_analysis=parallel_analysis,
        )

        # Step 4: Determine if failure is related to recent changes
        is_related = self._is_failure_related_to_changes(
            failure=failure,
            changed_files=changed_files or [],
        )

        # Step 5: Calculate overall confidence
        analysis_confidence = self._calculate_analysis_confidence(
            root_causes=root_causes,
            fix_suggestions=fix_suggestions,
            provider_count=len(parallel_analysis.responses),
        )

        return FailureAnalysis(
            test_failure=failure,
            root_causes=root_causes,
            fix_suggestions=fix_suggestions,
            is_related_to_changes=is_related,
            multi_agent_responses=parallel_analysis.responses,
            analysis_confidence=analysis_confidence,
        )

    def _run_parallel_analysis(
        self,
        failure: TestFailure,
        framework: TestFramework,
        changed_files: Optional[List[str]],
        codebase_context: Optional[str],
    ) -> MultiAgentResponse:
        """Run parallel analysis with multiple AI providers.

        Args:
            failure: Test failure to analyze
            framework: Test framework used
            changed_files: Recently changed files
            codebase_context: Additional context

        Returns:
            MultiAgentResponse with perspectives from all providers
        """
        # Build context-rich prompt
        changed_files_str = "\n".join([f"- {f}" for f in (changed_files or [])])
        context_str = (
            f"\n\n**Codebase Context:**\n{codebase_context}" if codebase_context else ""
        )

        prompt = f"""Analyze this test failure and provide:

1. **Root Cause**: What is the underlying cause of this failure?
2. **Category**: Classify as assertion_error, import_error, syntax_error, type_error, attribute_error, runtime_error, timeout, or unknown
3. **Confidence**: Rate your confidence in this analysis (0.0 to 1.0)
4. **Fix Strategy**: How would you fix this?
5. **Related to Changes**: Is this likely caused by recent changes? (yes/no)

**Test Framework:** {framework.value}
**Test Name:** {failure.test_name}
**Test File:** {failure.test_file}
**Error Message:** {failure.error_message}

**Stack Trace:**
{failure.stack_trace or 'Not available'}

**Recently Changed Files:**
{changed_files_str or 'None'}
{context_str}

Provide a structured analysis focusing on actionable insights.
"""

        return self.multi_agent_client.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.ALL,
            timeout=120,
        )

    def _extract_root_causes(
        self,
        failure: TestFailure,
        multi_agent_response: MultiAgentResponse,
    ) -> List[RootCause]:
        """Extract root causes from multi-agent responses.

        Args:
            failure: Test failure being analyzed
            multi_agent_response: Responses from multiple providers

        Returns:
            List of identified root causes
        """
        root_causes = []

        for provider, response in multi_agent_response.responses.items():
            # Parse root cause from response
            root_cause_match = re.search(
                r"\*\*Root Cause:\*\*\s*(.*?)(?=\n\*\*|\n\n|$)",
                response,
                re.DOTALL | re.IGNORECASE,
            )

            category_match = re.search(
                r"\*\*Category:\*\*\s*(\w+)",
                response,
                re.IGNORECASE,
            )

            confidence_match = re.search(
                r"\*\*Confidence:\*\*\s*([\d.]+)",
                response,
                re.IGNORECASE,
            )

            if root_cause_match:
                description = root_cause_match.group(1).strip()

                # Parse category
                category = FailureCategory.UNKNOWN
                if category_match:
                    cat_str = category_match.group(1).lower()
                    try:
                        category = FailureCategory(cat_str)
                    except ValueError:
                        self.logger.warning(
                            "Unknown failure category",
                            category=cat_str,
                            provider=provider,
                        )

                # Parse confidence
                confidence = 0.7  # Default
                if confidence_match:
                    try:
                        confidence = float(confidence_match.group(1))
                        confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
                    except ValueError:
                        pass

                root_causes.append(
                    RootCause(
                        description=description,
                        category=category,
                        confidence=confidence,
                        affected_files=[failure.test_file],
                        related_failures=[failure.test_name],
                    )
                )

        return root_causes

    def _synthesize_fix_suggestions(
        self,
        failure: TestFailure,
        root_causes: List[RootCause],
        parallel_analysis: MultiAgentResponse,
    ) -> List[FixSuggestion]:
        """Synthesize fix suggestions using dialectical approach.

        Args:
            failure: Test failure being analyzed
            root_causes: Identified root causes
            parallel_analysis: Initial parallel analysis results

        Returns:
            List of synthesized fix suggestions
        """
        if not parallel_analysis.success or not parallel_analysis.responses:
            self.logger.warning("No parallel analysis available for synthesis")
            return []

        # Build synthesis prompt from parallel analyses
        analyses_summary = "\n\n".join(
            [
                f"**{provider.upper()} Analysis:**\n{response}"
                for provider, response in parallel_analysis.responses.items()
            ]
        )

        root_causes_summary = "\n".join(
            [
                f"- {rc.description} (confidence: {rc.confidence:.2f})"
                for rc in root_causes
            ]
        )

        prompt = f"""Synthesize the best fix approach from multiple AI analyses.

**Test Failure:** {failure.test_name}
**Error:** {failure.error_message}

**Identified Root Causes:**
{root_causes_summary}

**Multiple AI Analyses:**
{analyses_summary}

**Task:**
1. Compare the different fix strategies proposed above
2. Identify the most promising approach (THESIS)
3. Consider potential issues with that approach (ANTITHESIS)
4. Propose a refined fix that addresses concerns (SYNTHESIS)

**Provide:**
1. **Recommended Fix**: Clear description of the fix
2. **File to Modify**: Which file needs changes
3. **Proposed Changes**: Specific code changes
4. **Success Probability**: Estimate (0.0 to 1.0)
5. **Rationale**: Why this approach is best
6. **Alternatives**: Other viable approaches

Be specific and actionable.
"""

        synthesis_response = self.multi_agent_client.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.DIALECTICAL,
            timeout=180,
        )

        if not synthesis_response.success:
            self.logger.warning("Dialectical synthesis failed")
            return []

        # Parse fix suggestions from synthesis
        fix_suggestions = []

        for provider, response in synthesis_response.responses.items():
            fix_match = re.search(
                r"\*\*Recommended Fix:\*\*\s*(.*?)(?=\n\*\*|\n\n|$)",
                response,
                re.DOTALL | re.IGNORECASE,
            )

            file_match = re.search(
                r"\*\*File to Modify:\*\*\s*(.*?)(?=\n|$)",
                response,
                re.IGNORECASE,
            )

            changes_match = re.search(
                r"\*\*Proposed Changes:\*\*\s*(.*?)(?=\n\*\*|\n\n|$)",
                response,
                re.DOTALL | re.IGNORECASE,
            )

            prob_match = re.search(
                r"\*\*Success Probability:\*\*\s*([\d.]+)",
                response,
                re.IGNORECASE,
            )

            rationale_match = re.search(
                r"\*\*Rationale:\*\*\s*(.*?)(?=\n\*\*|\n\n|$)",
                response,
                re.DOTALL | re.IGNORECASE,
            )

            if fix_match and file_match and changes_match:
                success_prob = 0.7  # Default
                if prob_match:
                    try:
                        success_prob = float(prob_match.group(1))
                        success_prob = max(0.0, min(1.0, success_prob))
                    except ValueError:
                        pass

                fix_suggestions.append(
                    FixSuggestion(
                        description=fix_match.group(1).strip(),
                        file_path=file_match.group(1).strip(),
                        proposed_changes=changes_match.group(1).strip(),
                        success_probability=success_prob,
                        rationale=(
                            rationale_match.group(1).strip() if rationale_match else ""
                        ),
                        provider_consensus=synthesis_response.responses,
                    )
                )

        return fix_suggestions

    def _is_failure_related_to_changes(
        self,
        failure: TestFailure,
        changed_files: List[str],
    ) -> bool:
        """Determine if failure is likely related to recent changes.

        Args:
            failure: Test failure to check
            changed_files: List of recently changed files

        Returns:
            True if failure is likely related to changes
        """
        if not changed_files:
            return False

        # Check if test file was changed
        if failure.test_file in changed_files:
            return True

        # Check if any changed file is imported/referenced in stack trace
        if failure.stack_trace:
            for changed_file in changed_files:
                file_name = Path(changed_file).name
                if file_name in failure.stack_trace:
                    return True

        return False

    def _calculate_analysis_confidence(
        self,
        root_causes: List[RootCause],
        fix_suggestions: List[FixSuggestion],
        provider_count: int,
    ) -> float:
        """Calculate overall confidence in the analysis.

        Args:
            root_causes: Identified root causes
            fix_suggestions: Generated fix suggestions
            provider_count: Number of providers that responded

        Returns:
            Confidence score between 0.0 and 1.0
        """
        if not root_causes or not fix_suggestions:
            return 0.0

        # Average root cause confidence
        avg_rc_confidence = sum(rc.confidence for rc in root_causes) / len(root_causes)

        # Average fix suggestion probability
        avg_fix_prob = sum(fs.success_probability for fs in fix_suggestions) / len(
            fix_suggestions
        )

        # Provider consensus boost (more providers = higher confidence)
        provider_factor = min(1.0, provider_count / 3.0)  # Max at 3 providers

        # Weighted average
        confidence = (
            avg_rc_confidence * 0.4 + avg_fix_prob * 0.4 + provider_factor * 0.2
        )

        return min(1.0, confidence)

    def should_attempt_auto_fix(self, analysis: FailureAnalysis) -> bool:
        """Determine if auto-fix should be attempted.

        Args:
            analysis: Failure analysis to check

        Returns:
            True if auto-fix should be attempted
        """
        # Must have at least one fix suggestion
        if not analysis.fix_suggestions:
            return False

        # Must meet minimum confidence threshold
        if analysis.analysis_confidence < self.min_confidence_threshold:
            return False

        # At least one fix must have high success probability
        max_fix_prob = max(fs.success_probability for fs in analysis.fix_suggestions)
        return max_fix_prob >= self.min_confidence_threshold

    def get_best_fix(self, analysis: FailureAnalysis) -> Optional[FixSuggestion]:
        """Get the fix suggestion with highest success probability.

        Args:
            analysis: Failure analysis

        Returns:
            Best fix suggestion or None
        """
        if not analysis.fix_suggestions:
            return None

        return max(analysis.fix_suggestions, key=lambda fs: fs.success_probability)

    def get_statistics(self) -> Dict[str, Any]:
        """Get analyzer statistics.

        Returns:
            Dictionary with usage statistics
        """
        success_rate = (
            self.successful_analyses / self.total_analyses
            if self.total_analyses > 0
            else 0.0
        )

        return {
            "total_analyses": self.total_analyses,
            "successful_analyses": self.successful_analyses,
            "failed_analyses": self.failed_analyses,
            "success_rate": success_rate,
        }

    def reset_statistics(self):
        """Reset analyzer statistics."""
        self.total_analyses = 0
        self.successful_analyses = 0
        self.failed_analyses = 0
