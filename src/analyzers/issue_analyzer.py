"""Issue analysis using multi-agent-coder for enhanced intelligence."""

import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from github.Issue import Issue

from ..core.logger import AuditLogger, EventType
from ..integrations.multi_agent_coder_client import (MultiAgentCoderClient,
                                                     MultiAgentResponse)


class IssueType(Enum):
    """Types of issues."""

    BUG = "bug"
    FEATURE = "feature"
    REFACTOR = "refactor"
    DOCUMENTATION = "documentation"
    TEST = "test"
    CHORE = "chore"
    UNKNOWN = "unknown"


@dataclass
class IssueAnalysis:
    """Analysis result for a GitHub issue."""

    issue_number: int
    issue_type: IssueType
    complexity_score: int  # 0-10
    is_actionable: bool
    actionability_reason: str
    key_requirements: List[str]
    affected_files: List[str]
    risks: List[str]
    recommended_approach: str

    # Multi-agent analysis
    provider_analyses: Dict[str, str]
    consensus_confidence: float  # 0.0-1.0

    # Metadata
    total_tokens: int
    total_cost: float
    analysis_success: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        result["issue_type"] = self.issue_type.value
        return result


class IssueAnalyzer:
    """Analyzes GitHub issues using multi-agent-coder for enhanced intelligence.

    Uses multiple AI providers (Anthropic, OpenAI, DeepSeek) to:
    - Classify issue type
    - Assess complexity
    - Validate actionability
    - Extract requirements
    - Identify affected files
    - Provide implementation recommendations
    """

    # Complexity score thresholds
    MAX_COMPLEXITY = 10
    COMPLEXITY_TRIVIAL = 2
    COMPLEXITY_SIMPLE = 4
    COMPLEXITY_MODERATE = 6
    COMPLEXITY_COMPLEX = 8

    def __init__(
        self,
        multi_agent_client: MultiAgentCoderClient,
        logger: AuditLogger,
        max_complexity_threshold: int = 7,
    ):
        """Initialize issue analyzer.

        Args:
            multi_agent_client: Multi-agent-coder client instance
            logger: Audit logger instance
            max_complexity_threshold: Maximum complexity to accept (0-10)
        """
        self.multi_agent = multi_agent_client
        self.logger = logger
        self.max_complexity_threshold = max_complexity_threshold

        # Statistics
        self.analyses_performed = 0
        self.actionable_count = 0
        self.complexity_rejected_count = 0

    def analyze_issue(self, issue: Issue) -> IssueAnalysis:
        """Analyze a GitHub issue using multi-agent-coder.

        Args:
            issue: GitHub Issue object to analyze

        Returns:
            IssueAnalysis with comprehensive analysis results
        """
        self.logger.info(
            f"Analyzing issue #{issue.number}",
            issue_number=issue.number,
            title=issue.title,
        )

        try:
            # Get multi-agent analysis
            response = self.multi_agent.analyze_issue(
                issue_title=issue.title,
                issue_body=issue.body or "",
                labels=[label.name for label in issue.labels],
            )

            if not response.success:
                self.logger.error(
                    f"Multi-agent analysis failed for issue #{issue.number}",
                    issue_number=issue.number,
                    error=response.error,
                )
                return self._create_failed_analysis(
                    issue.number, response.error or "Unknown error"
                )

            # Parse and synthesize responses from multiple providers
            analysis = self._synthesize_analyses(issue.number, response)

            # Update statistics
            self.analyses_performed += 1
            if analysis.is_actionable:
                self.actionable_count += 1
            if analysis.complexity_score > self.max_complexity_threshold:
                self.complexity_rejected_count += 1

            # Log analysis result
            self.logger.audit(
                EventType.ISSUE_ANALYZED,
                f"Analyzed issue #{issue.number}: {analysis.issue_type.value}, complexity={analysis.complexity_score}",
                resource_type="issue",
                resource_id=str(issue.number),
                metadata=analysis.to_dict(),
            )

            self.logger.info(
                f"Issue #{issue.number} analysis complete",
                issue_number=issue.number,
                issue_type=analysis.issue_type.value,
                complexity=analysis.complexity_score,
                actionable=analysis.is_actionable,
                providers=list(response.responses.keys()),
            )

            return analysis

        except Exception as e:
            self.logger.error(
                f"Error analyzing issue #{issue.number}",
                issue_number=issue.number,
                error=str(e),
                exc_info=True,
            )
            return self._create_failed_analysis(issue.number, str(e))

    def _synthesize_analyses(
        self,
        issue_number: int,
        response: MultiAgentResponse,
    ) -> IssueAnalysis:
        """Synthesize multiple provider responses into single analysis.

        Args:
            issue_number: GitHub issue number
            response: Multi-agent response with provider analyses

        Returns:
            Synthesized IssueAnalysis
        """
        # Extract information from each provider's response
        issue_types = []
        complexity_scores = []
        actionability_votes = []
        requirements_sets = []
        affected_files_sets = []
        risks_sets = []
        approaches = []

        for provider, analysis_text in response.responses.items():
            # Parse issue type
            issue_type = self._extract_issue_type(analysis_text)
            if issue_type:
                issue_types.append(issue_type)

            # Parse complexity score
            complexity = self._extract_complexity_score(analysis_text)
            if complexity is not None:
                complexity_scores.append(complexity)

            # Parse actionability
            actionable, reason = self._extract_actionability(analysis_text)
            if actionable is not None:
                actionability_votes.append((actionable, reason))

            # Extract requirements
            requirements = self._extract_requirements(analysis_text)
            if requirements:
                requirements_sets.append(requirements)

            # Extract affected files
            files = self._extract_affected_files(analysis_text)
            if files:
                affected_files_sets.append(files)

            # Extract risks
            risks = self._extract_risks(analysis_text)
            if risks:
                risks_sets.append(risks)

            # Extract approach
            approach = self._extract_approach(analysis_text)
            if approach:
                approaches.append(approach)

        # Synthesize results using consensus/averaging
        final_issue_type = self._consensus_issue_type(issue_types)
        final_complexity = self._average_complexity(complexity_scores)
        final_actionable, final_reason = self._consensus_actionability(
            actionability_votes
        )
        final_requirements = self._merge_requirements(requirements_sets)
        final_files = self._merge_files(affected_files_sets)
        final_risks = self._merge_risks(risks_sets)
        final_approach = self._synthesize_approaches(approaches)

        # Calculate consensus confidence
        confidence = self._calculate_consensus_confidence(
            len(issue_types),
            len(complexity_scores),
            len(actionability_votes),
            len(response.providers),
        )

        return IssueAnalysis(
            issue_number=issue_number,
            issue_type=final_issue_type,
            complexity_score=final_complexity,
            is_actionable=final_actionable,
            actionability_reason=final_reason,
            key_requirements=final_requirements,
            affected_files=final_files,
            risks=final_risks,
            recommended_approach=final_approach,
            provider_analyses=response.responses,
            consensus_confidence=confidence,
            total_tokens=response.total_tokens,
            total_cost=response.total_cost,
            analysis_success=True,
        )

    def _extract_issue_type(self, text: str) -> Optional[IssueType]:
        """Extract issue type from analysis text."""
        text_lower = text.lower()

        # Look for explicit issue type mentions
        type_patterns = {
            IssueType.BUG: ["bug", "defect", "error", "issue"],
            IssueType.FEATURE: ["feature", "enhancement", "new functionality"],
            IssueType.REFACTOR: ["refactor", "refactoring", "restructure"],
            IssueType.DOCUMENTATION: ["documentation", "docs", "readme"],
            IssueType.TEST: ["test", "testing", "test coverage"],
            IssueType.CHORE: ["chore", "maintenance", "cleanup"],
        }

        # Find most mentioned type
        type_counts = {}
        for issue_type, patterns in type_patterns.items():
            count = sum(text_lower.count(pattern) for pattern in patterns)
            if count > 0:
                type_counts[issue_type] = count

        if type_counts:
            return max(type_counts, key=type_counts.get)

        return IssueType.UNKNOWN

    def _extract_complexity_score(self, text: str) -> Optional[int]:
        """Extract complexity score from analysis text."""
        # Look for patterns like "complexity: 7", "score: 8/10", "7 out of 10"
        patterns = [
            r"complexity[:\s]+(\d+)",
            r"score[:\s]+(\d+)",
            r"(\d+)\s*(?:/\s*10|out of 10)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                try:
                    score = int(match.group(1))
                    return min(max(score, 0), self.MAX_COMPLEXITY)
                except ValueError:
                    continue

        return None

    def _extract_actionability(self, text: str) -> tuple[Optional[bool], str]:
        """Extract actionability decision from analysis text."""
        text_lower = text.lower()

        # Look for explicit yes/no
        if re.search(r"actionab(?:le|ility)[:\s]+yes", text_lower):
            reason_match = re.search(
                r"actionab(?:le|ility)[:\s]+yes[^.]*\.([^.]+)", text_lower
            )
            reason = (
                reason_match.group(1).strip()
                if reason_match
                else "Analysis indicates issue is actionable"
            )
            return True, reason

        if re.search(r"actionab(?:le|ility)[:\s]+no", text_lower):
            reason_match = re.search(
                r"actionab(?:le|ility)[:\s]+no[^.]*\.([^.]+)", text_lower
            )
            reason = (
                reason_match.group(1).strip()
                if reason_match
                else "Analysis indicates issue is not actionable"
            )
            return False, reason

        # Heuristic: if we can extract requirements, likely actionable
        if "requirement" in text_lower and "unclear" not in text_lower:
            return True, "Clear requirements found in analysis"

        return None, ""

    def _extract_requirements(self, text: str) -> List[str]:
        """Extract key requirements from analysis text."""
        requirements = []

        # Look for numbered or bulleted lists of requirements
        requirement_section = re.search(
            r"(?:key requirements?|requirements?)[:\s]+(.*?)(?:\n\n|\*\*|$)",
            text.lower(),
            re.DOTALL,
        )

        if requirement_section:
            section_text = requirement_section.group(1)
            # Extract items from numbered or bulleted lists
            items = re.findall(
                r"(?:^\s*(?:\d+\.|-|\*)\s+(.+)$)", section_text, re.MULTILINE
            )
            requirements.extend([item.strip() for item in items if item.strip()])

        return requirements[:5]  # Limit to 5 key requirements

    def _extract_affected_files(self, text: str) -> List[str]:
        """Extract likely affected files from analysis text."""
        files = []

        # Look for file paths or file mentions
        file_patterns = [
            r"(\w+/[\w/]+\.py)",  # Python file paths
            r"(\w+\.py)",  # Python files
            r"(src/[\w/]+)",  # Source paths
        ]

        for pattern in file_patterns:
            matches = re.findall(pattern, text)
            files.extend(matches)

        return list(set(files))[:10]  # Unique, limit to 10

    def _extract_risks(self, text: str) -> List[str]:
        """Extract identified risks from analysis text."""
        risks = []

        # Look for risks section
        risk_section = re.search(
            r"(?:risks?|challenges?)[:\s]+(.*?)(?:\n\n|\*\*|$)", text.lower(), re.DOTALL
        )

        if risk_section:
            section_text = risk_section.group(1)
            items = re.findall(
                r"(?:^\s*(?:\d+\.|-|\*)\s+(.+)$)", section_text, re.MULTILINE
            )
            risks.extend([item.strip() for item in items if item.strip()])

        return risks[:5]  # Limit to 5 key risks

    def _extract_approach(self, text: str) -> str:
        """Extract recommended approach from analysis text."""
        approach_section = re.search(
            r"(?:recommended approach|approach)[:\s]+(.*?)(?:\n\n|\*\*|$)",
            text.lower(),
            re.DOTALL,
        )

        if approach_section:
            return approach_section.group(1).strip()

        return ""

    def _consensus_issue_type(self, types: List[IssueType]) -> IssueType:
        """Determine consensus issue type from multiple provider votes."""
        if not types:
            return IssueType.UNKNOWN

        # Return most common type
        type_counts = {}
        for issue_type in types:
            type_counts[issue_type] = type_counts.get(issue_type, 0) + 1

        return max(type_counts, key=type_counts.get)

    def _average_complexity(self, scores: List[int]) -> int:
        """Calculate average complexity score."""
        if not scores:
            return 5  # Default to moderate complexity

        return min(round(sum(scores) / len(scores)), self.MAX_COMPLEXITY)

    def _consensus_actionability(
        self, votes: List[tuple[bool, str]]
    ) -> tuple[bool, str]:
        """Determine consensus on actionability."""
        if not votes:
            return False, "No actionability determination from providers"

        # Majority vote
        yes_votes = sum(1 for actionable, _ in votes if actionable)
        no_votes = len(votes) - yes_votes

        if yes_votes > no_votes:
            # Use most detailed reason from yes votes
            reasons = [reason for actionable, reason in votes if actionable and reason]
            return True, (
                reasons[0] if reasons else "Majority of providers indicate actionable"
            )
        else:
            reasons = [
                reason for actionable, reason in votes if not actionable and reason
            ]
            return False, (
                reasons[0]
                if reasons
                else "Majority of providers indicate not actionable"
            )

    def _merge_requirements(self, requirements_sets: List[List[str]]) -> List[str]:
        """Merge requirements from multiple providers."""
        all_requirements = []
        for req_set in requirements_sets:
            all_requirements.extend(req_set)

        # Deduplicate while preserving order
        seen = set()
        unique_requirements = []
        for req in all_requirements:
            req_lower = req.lower()
            if req_lower not in seen:
                seen.add(req_lower)
                unique_requirements.append(req)

        return unique_requirements[:5]  # Top 5 requirements

    def _merge_files(self, files_sets: List[List[str]]) -> List[str]:
        """Merge affected files from multiple providers."""
        all_files = []
        for file_set in files_sets:
            all_files.extend(file_set)

        return list(set(all_files))[:10]  # Unique, top 10

    def _merge_risks(self, risks_sets: List[List[str]]) -> List[str]:
        """Merge risks from multiple providers."""
        all_risks = []
        for risk_set in risks_sets:
            all_risks.extend(risk_set)

        # Deduplicate
        seen = set()
        unique_risks = []
        for risk in all_risks:
            risk_lower = risk.lower()
            if risk_lower not in seen:
                seen.add(risk_lower)
                unique_risks.append(risk)

        return unique_risks[:5]  # Top 5 risks

    def _synthesize_approaches(self, approaches: List[str]) -> str:
        """Synthesize recommended approaches from multiple providers."""
        if not approaches:
            return "No specific approach recommended"

        # If multiple similar approaches, pick longest/most detailed
        # Simple heuristic: return longest approach
        return max(approaches, key=len) if approaches else ""

    def _calculate_consensus_confidence(
        self,
        type_count: int,
        complexity_count: int,
        actionability_count: int,
        total_providers: int,
    ) -> float:
        """Calculate confidence in consensus based on provider agreement.

        Args:
            type_count: Number of providers that provided type classification
            complexity_count: Number of providers that provided complexity score
            actionability_count: Number of providers that provided actionability
            total_providers: Total number of providers queried

        Returns:
            Confidence score from 0.0 to 1.0
        """
        if total_providers == 0:
            return 0.0

        # Average of response rates across categories
        type_rate = type_count / total_providers
        complexity_rate = complexity_count / total_providers
        actionability_rate = actionability_count / total_providers

        return (type_rate + complexity_rate + actionability_rate) / 3

    def _create_failed_analysis(self, issue_number: int, error: str) -> IssueAnalysis:
        """Create a failed analysis result.

        Args:
            issue_number: GitHub issue number
            error: Error message

        Returns:
            IssueAnalysis marked as failed
        """
        return IssueAnalysis(
            issue_number=issue_number,
            issue_type=IssueType.UNKNOWN,
            complexity_score=10,  # Maximum complexity to prevent auto-processing
            is_actionable=False,
            actionability_reason=f"Analysis failed: {error}",
            key_requirements=[],
            affected_files=[],
            risks=[f"Analysis failed: {error}"],
            recommended_approach="Manual review required",
            provider_analyses={},
            consensus_confidence=0.0,
            total_tokens=0,
            total_cost=0.0,
            analysis_success=False,
        )

    def get_statistics(self) -> Dict[str, Any]:
        """Get analyzer statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "analyses_performed": self.analyses_performed,
            "actionable_count": self.actionable_count,
            "complexity_rejected_count": self.complexity_rejected_count,
            "actionable_percentage": (
                (self.actionable_count / self.analyses_performed * 100)
                if self.analyses_performed > 0
                else 0
            ),
            "multi_agent_stats": self.multi_agent.get_statistics(),
        }

    def reset_statistics(self):
        """Reset statistics."""
        self.analyses_performed = 0
        self.actionable_count = 0
        self.complexity_rejected_count = 0
        self.multi_agent.reset_statistics()
