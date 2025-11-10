"""Failure analysis using multi-agent perspectives.

Analyzes failed operations to extract lessons learned and improve safety guards.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..core.logger import AuditLogger
from ..integrations.multi_agent_coder_client import (
    MultiAgentCoderClient,
    MultiAgentStrategy,
)


@dataclass
class LessonsLearned:
    """Lessons extracted from failure analysis."""

    root_cause: str
    why_not_caught: str
    prevention_measures: List[str]
    should_update_complexity_threshold: bool = False
    recommended_threshold: Optional[int] = None
    should_add_guard: bool = False
    guard_definition: Optional[str] = None
    summary: str = ""
    confidence: float = 0.0  # 0.0-1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "root_cause": self.root_cause,
            "why_not_caught": self.why_not_caught,
            "prevention_measures": self.prevention_measures,
            "should_update_complexity_threshold": self.should_update_complexity_threshold,
            "recommended_threshold": self.recommended_threshold,
            "should_add_guard": self.should_add_guard,
            "guard_definition": self.guard_definition,
            "summary": self.summary,
            "confidence": self.confidence,
        }


@dataclass
class FailureAnalysis:
    """Complete failure analysis from multi-agent perspectives."""

    failure_id: str
    work_item_description: str
    failure_reason: str
    lessons_learned: LessonsLearned
    provider_perspectives: Dict[str, str]  # provider -> analysis
    consensus_reached: bool
    analyzed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "failure_id": self.failure_id,
            "work_item_description": self.work_item_description,
            "failure_reason": self.failure_reason,
            "lessons_learned": self.lessons_learned.to_dict(),
            "provider_perspectives": self.provider_perspectives,
            "consensus_reached": self.consensus_reached,
            "analyzed_at": self.analyzed_at.isoformat(),
        }


class FailureAnalyzer:
    """Analyzes failures using multiple AI perspectives to extract lessons.

    Responsibilities:
    - Perform root cause analysis using multi-agent
    - Identify why failures weren't caught earlier
    - Suggest prevention measures
    - Recommend guard updates
    - Extract actionable lessons
    """

    def __init__(
        self,
        multi_agent_client: MultiAgentCoderClient,
        logger: AuditLogger,
    ):
        """Initialize failure analyzer.

        Args:
            multi_agent_client: Multi-agent-coder client
            logger: Audit logger
        """
        self.multi_agent_client = multi_agent_client
        self.logger = logger

        self.logger.info("failure_analyzer_initialized")

    def analyze_failure(
        self,
        failure_id: str,
        work_item_description: str,
        changes_summary: str,
        failure_reason: str,
        test_output: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None,
    ) -> FailureAnalysis:
        """Analyze a failure using multi-agent perspectives.

        Args:
            failure_id: Unique failure identifier
            work_item_description: Description of what was attempted
            changes_summary: Summary of changes made
            failure_reason: Why it failed
            test_output: Optional test output
            additional_context: Optional additional context

        Returns:
            FailureAnalysis with lessons learned
        """
        self.logger.info(
            "analyzing_failure",
            failure_id=failure_id,
            work_item=work_item_description,
        )

        # Build comprehensive analysis prompt
        prompt = self._build_analysis_prompt(
            work_item_description=work_item_description,
            changes_summary=changes_summary,
            failure_reason=failure_reason,
            test_output=test_output,
            additional_context=additional_context,
        )

        # Query all providers for multi-perspective analysis
        response = self.multi_agent_client.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.DIALECTICAL,  # Thesis → Antithesis → Synthesis
            timeout=240,  # 4 minutes for thorough analysis
        )

        if not response.success:
            self.logger.error(
                "failure_analysis_failed",
                failure_id=failure_id,
                error=response.error,
            )
            # Return basic analysis on failure
            return FailureAnalysis(
                failure_id=failure_id,
                work_item_description=work_item_description,
                failure_reason=failure_reason,
                lessons_learned=LessonsLearned(
                    root_cause="Analysis failed",
                    why_not_caught="Unknown",
                    prevention_measures=[],
                    summary="Failed to analyze failure",
                ),
                provider_perspectives={},
                consensus_reached=False,
            )

        # Extract lessons from responses
        lessons = self._extract_lessons(response, work_item_description, failure_reason)

        # Check consensus
        consensus = self._check_consensus(response)

        analysis = FailureAnalysis(
            failure_id=failure_id,
            work_item_description=work_item_description,
            failure_reason=failure_reason,
            lessons_learned=lessons,
            provider_perspectives=response.responses,
            consensus_reached=consensus,
        )

        self.logger.info(
            "failure_analyzed",
            failure_id=failure_id,
            consensus_reached=consensus,
            should_update_guards=lessons.should_add_guard,
        )

        return analysis

    def analyze_failure_patterns(
        self,
        recent_failures: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Analyze patterns across multiple failures.

        Args:
            recent_failures: List of recent failure data

        Returns:
            Dict with pattern analysis
        """
        self.logger.info(
            "analyzing_failure_patterns",
            failure_count=len(recent_failures),
        )

        # Build pattern analysis prompt
        failures_summary = "\n\n".join(
            [
                f"**Failure {i+1}**:\n"
                f"- Work Item: {f.get('work_item_description', 'Unknown')}\n"
                f"- Reason: {f.get('failure_reason', 'Unknown')}\n"
                f"- Changes: {f.get('changes_summary', 'Unknown')}"
                for i, f in enumerate(recent_failures)
            ]
        )

        prompt = f"""Analyze these failure patterns:

{failures_summary}

Identify:
1. **Common Root Causes**: Are there systematic issues?
2. **Guard Gaps**: What types of problems are our safety guards missing?
3. **Process Improvements**: How can we prevent these classes of failures?
4. **Complexity Calibration**: Is our complexity threshold appropriate?

Provide specific, actionable recommendations."""

        response = self.multi_agent_client.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.ALL,
            timeout=300,
        )

        # Extract patterns
        patterns = self._extract_patterns(response)

        self.logger.info(
            "failure_patterns_analyzed",
            failure_count=len(recent_failures),
            patterns_found=len(patterns.get("common_causes", [])),
        )

        return patterns

    def _build_analysis_prompt(
        self,
        work_item_description: str,
        changes_summary: str,
        failure_reason: str,
        test_output: Optional[str],
        additional_context: Optional[Dict[str, Any]],
    ) -> str:
        """Build comprehensive failure analysis prompt."""

        test_section = ""
        if test_output:
            test_section = f"\n**Test Output**:\n```\n{test_output[:2000]}\n{'...' if len(test_output) > 2000 else ''}\n```"

        context_section = ""
        if additional_context:
            context_section = f"\n**Additional Context**: {additional_context}"

        return f"""Analyze this failure and extract lessons learned:

**Work Item**: {work_item_description}

**Changes Made**: {changes_summary}

**Failure Reason**: {failure_reason}
{test_section}{context_section}

Please provide:

1. **Root Cause Analysis**:
   - What was the fundamental cause of this failure?
   - Was it a technical issue, process issue, or complexity issue?

2. **Why Wasn't This Caught Earlier?**:
   - Should our safety guards have caught this?
   - Was the complexity estimate accurate?
   - Were there warning signs we missed?

3. **Prevention Measures** (be specific):
   - What guard rule would have caught this?
   - Should we lower complexity threshold?
   - What file patterns should we protect?
   - What tests should we add?

4. **Recommendations**:
   - Should we add a new safety guard? (YES/NO)
   - If yes, describe the guard pattern
   - Should we adjust complexity threshold? (YES/NO)
   - If yes, what should the new threshold be?

5. **Summary**: One sentence lesson learned.

Be specific and actionable in your recommendations."""

    def _extract_lessons(
        self,
        response,
        work_item_description: str,
        failure_reason: str,
    ) -> LessonsLearned:
        """Extract lessons learned from multi-agent responses."""

        # Aggregate all responses
        all_text = "\n\n".join(response.responses.values())

        # Extract root cause
        root_cause = self._extract_section(all_text, "root cause")
        if not root_cause:
            root_cause = f"Failed while: {work_item_description}"

        # Extract why not caught
        why_not_caught = self._extract_section(all_text, "why wasn't")
        if not why_not_caught:
            why_not_caught = "Guards did not detect this risk pattern"

        # Extract prevention measures
        prevention_measures = self._extract_list_items(all_text, "prevention")

        # Check if should add guard
        should_add_guard = (
            "YES" in all_text.upper()
            and "ADD" in all_text.upper()
            and "GUARD" in all_text.upper()
        )
        guard_definition = None
        if should_add_guard:
            guard_definition = self._extract_section(all_text, "guard pattern")

        # Check if should update threshold
        should_update_threshold = (
            "YES" in all_text.upper() and "THRESHOLD" in all_text.upper()
        )
        recommended_threshold = None
        if should_update_threshold:
            # Try to extract threshold number
            import re

            threshold_match = re.search(r"threshold.*?(\d+)", all_text, re.IGNORECASE)
            if threshold_match:
                recommended_threshold = int(threshold_match.group(1))

        # Extract summary
        summary = self._extract_section(all_text, "summary")
        if not summary:
            summary = f"Failure: {failure_reason}"

        return LessonsLearned(
            root_cause=root_cause,
            why_not_caught=why_not_caught,
            prevention_measures=prevention_measures,
            should_update_complexity_threshold=should_update_threshold,
            recommended_threshold=recommended_threshold,
            should_add_guard=should_add_guard,
            guard_definition=guard_definition,
            summary=summary,
            confidence=0.8 if len(response.responses) >= 3 else 0.6,
        )

    def _extract_section(self, text: str, section_keyword: str) -> str:
        """Extract content from a section."""
        lines = text.split("\n")
        in_section = False
        section_lines = []

        for line in lines:
            line_lower = line.lower()

            # Check if entering section
            if section_keyword in line_lower and (":" in line or "**" in line):
                in_section = True
                # Extract content after colon if on same line
                if ":" in line:
                    content = line.split(":", 1)[1].strip()
                    if content and not content.startswith("*"):
                        section_lines.append(content)
                continue

            # Check if leaving section (new header)
            if in_section and ("**" in line or line.startswith("#")):
                break

            # Collect section lines
            if in_section and line.strip():
                section_lines.append(line.strip())

        return " ".join(section_lines[:3])  # First 3 lines

    def _extract_list_items(self, text: str, section_keyword: str) -> List[str]:
        """Extract list items from a section."""
        lines = text.split("\n")
        in_section = False
        items = []

        for line in lines:
            line_lower = line.lower()

            if section_keyword in line_lower:
                in_section = True
                continue

            if in_section and ("**" in line or line.startswith("#")):
                break

            if in_section and (
                line.strip().startswith("-") or line.strip().startswith("*")
            ):
                item = line.strip().lstrip("-*").strip()
                if item:
                    items.append(item)

        return items[:5]  # Top 5 items

    def _check_consensus(self, response) -> bool:
        """Check if providers reached consensus."""
        # Simple heuristic: check if key terms appear in multiple responses
        key_terms_count = {}

        for provider_response in response.responses.values():
            words = provider_response.lower().split()
            for word in set(words):
                if len(word) > 5:  # Ignore short words
                    key_terms_count[word] = key_terms_count.get(word, 0) + 1

        # Consensus if multiple providers mention same key terms
        consensus_terms = [
            term for term, count in key_terms_count.items() if count >= 2
        ]
        return len(consensus_terms) >= 5

    def _extract_patterns(self, response) -> Dict[str, Any]:
        """Extract patterns from pattern analysis response."""
        all_text = "\n\n".join(response.responses.values())

        return {
            "common_causes": self._extract_list_items(all_text, "common"),
            "guard_gaps": self._extract_list_items(all_text, "guard"),
            "process_improvements": self._extract_list_items(all_text, "process"),
            "complexity_calibration": self._extract_section(all_text, "complexity"),
        }
