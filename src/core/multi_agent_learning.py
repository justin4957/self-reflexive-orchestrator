"""Multi-agent learning system using multi-agent-coder for analysis.

Coordinates multi-agent analysis of failure patterns to generate improvements.
"""

import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from ..integrations.multi_agent_coder_client import (
    MultiAgentCoderClient,
    MultiAgentStrategy,
)
from .logger import AuditLogger
from .pattern_detector import FailurePattern


@dataclass
class RootCauseAnalysis:
    """Results of multi-agent root cause analysis."""

    pattern_id: str
    analyses: Dict[str, str]  # provider -> analysis
    consensus: Optional[str]
    confidence: float
    cost: float
    tokens_used: int


@dataclass
class LearningLesson:
    """Synthesized learning from dialectical process."""

    pattern_id: str
    thesis: str  # What went wrong
    antithesis: str  # Why it happened
    synthesis: str  # How to prevent
    actionable_items: List[str]
    confidence: float
    cost: float
    tokens_used: int


@dataclass
class ImprovementRecommendations:
    """Generated improvements from multi-agent analysis."""

    pattern_id: str
    prompt_improvements: Dict[str, str]  # prompt_id -> improved_prompt
    validation_rules: List[str]
    complexity_adjustments: Dict[str, Any]
    context_additions: List[str]
    consensus_score: float
    cost: float
    tokens_used: int


@dataclass
class EffectivenessValidation:
    """Validation of learning effectiveness."""

    pattern_id: str
    prevented_failures: bool
    failure_rate_before: float
    failure_rate_after: float
    side_effects: List[str]
    recommendation: str  # "keep", "refine", "revert"
    confidence: float
    cost: float
    tokens_used: int


class MultiAgentLearning:
    """Coordinates multi-agent learning from failure patterns.

    Responsibilities:
    - Perform multi-agent root cause analysis
    - Synthesize learning through dialectical process
    - Generate improvements with multi-agent consensus
    - Validate effectiveness of learning
    """

    def __init__(
        self,
        multi_agent_client: MultiAgentCoderClient,
        logger: AuditLogger,
    ):
        """Initialize multi-agent learning system.

        Args:
            multi_agent_client: Client for multi-agent-coder queries
            logger: Audit logger instance
        """
        self.multi_agent_client = multi_agent_client
        self.logger = logger

    def analyze_root_cause(self, pattern: FailurePattern) -> RootCauseAnalysis:
        """Perform multi-agent root cause analysis on failure pattern.

        Args:
            pattern: Detected failure pattern to analyze

        Returns:
            RootCauseAnalysis with multi-perspective insights
        """
        self.logger.info(
            "root_cause_analysis_started",
            pattern_id=pattern.pattern_id,
            failure_type=pattern.failure_type,
            occurrences=pattern.occurrence_count,
        )

        # Format failure examples
        failure_examples = self._format_failure_examples(pattern.failure_examples[:5])
        success_examples = self._format_success_examples(pattern.success_examples[:3])

        # Create analysis prompt
        prompt = f"""Analyze this failure pattern that has occurred {pattern.occurrence_count} times:

**Pattern Details:**
- Operation Type: {pattern.failure_type}
- Error Type: {pattern.error_type}
- Severity: {pattern.severity}
- Time Span: {pattern.first_seen} to {pattern.last_seen}
- Common Attributes: {json.dumps(pattern.common_attributes, indent=2)}

**Failure Examples:**
{failure_examples}

**Similar Successful Operations:**
{success_examples}

**Analysis Questions:**
From your perspective, analyze:
1. What is the root cause of these failures?
2. Why did similar operations succeed while these failed?
3. What patterns or commonalities do you observe?
4. What was the fundamental mistake or gap?
5. What assumptions or blind spots led to this failure?

Provide deep, actionable analysis, not surface-level observations.
Focus on what can be learned and improved.
"""

        # Execute multi-agent query with ALL strategy
        result = self.multi_agent_client.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.ALL,
        )

        # Extract analyses from different providers
        analyses = {}
        for response in result.responses:
            analyses[response.provider] = response.content

        # The multi-agent-coder should provide a summary
        consensus = result.summary if hasattr(result, "summary") else None

        # Calculate confidence based on agreement
        confidence = self._calculate_consensus_confidence(analyses)

        analysis = RootCauseAnalysis(
            pattern_id=pattern.pattern_id,
            analyses=analyses,
            consensus=consensus,
            confidence=confidence,
            cost=result.total_cost,
            tokens_used=result.total_tokens,
        )

        self.logger.info(
            "root_cause_analysis_completed",
            pattern_id=pattern.pattern_id,
            confidence=confidence,
            cost=result.total_cost,
        )

        return analysis

    def synthesize_learning(
        self, pattern: FailurePattern, root_cause: RootCauseAnalysis
    ) -> LearningLesson:
        """Synthesize learning through dialectical process.

        Args:
            pattern: Original failure pattern
            root_cause: Root cause analysis results

        Returns:
            LearningLesson with thesis, antithesis, synthesis
        """
        self.logger.info(
            "learning_synthesis_started",
            pattern_id=pattern.pattern_id,
        )

        # Format root cause analyses
        analyses_text = "\n\n".join(
            [
                f"**{provider}:** {analysis}"
                for provider, analysis in root_cause.analyses.items()
            ]
        )

        # Create dialectical learning prompt
        prompt = f"""Learn from these failure analyses using dialectical reasoning:

**Failure Pattern:**
- Type: {pattern.failure_type}
- Error: {pattern.error_type}
- Occurrences: {pattern.occurrence_count}
- Severity: {pattern.severity}

**Root Cause Analyses:**
{analyses_text}

**Dialectical Learning Process:**

**THESIS - What Went Wrong:**
Synthesize the different root cause analyses.
What fundamentally went wrong across all perspectives?
What is the core problem?

**ANTITHESIS - Why It Happened:**
Go deeper into the why.
Why didn't the system catch this earlier?
What assumptions or blind spots enabled this failure?
What was missing from our approach?

**SYNTHESIS - How to Prevent:**
What specific, actionable changes will prevent this failure?
Consider:
- Prompt template improvements
- Validation enhancements
- Error detection rules
- Process changes
- Context additions

Provide 3-5 concrete, actionable items.
Each should be specific enough to implement immediately.

Build consensus on the best prevention strategy across all perspectives.
"""

        # Execute with DIALECTICAL strategy
        result = self.multi_agent_client.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.DIALECTICAL,
        )

        # Parse the dialectical response
        content = (
            result.summary
            if hasattr(result, "summary")
            else result.responses[0].content
        )

        # Extract sections (simplified parsing)
        thesis = self._extract_section(content, "THESIS", "ANTITHESIS")
        antithesis = self._extract_section(content, "ANTITHESIS", "SYNTHESIS")
        synthesis = self._extract_section(content, "SYNTHESIS", None)

        # Extract actionable items
        actionable_items = self._extract_actionable_items(synthesis)

        # Calculate confidence
        confidence = self._calculate_consensus_confidence(
            {r.provider: r.content for r in result.responses}
        )

        lesson = LearningLesson(
            pattern_id=pattern.pattern_id,
            thesis=thesis,
            antithesis=antithesis,
            synthesis=synthesis,
            actionable_items=actionable_items,
            confidence=confidence,
            cost=result.total_cost,
            tokens_used=result.total_tokens,
        )

        self.logger.info(
            "learning_synthesis_completed",
            pattern_id=pattern.pattern_id,
            actionable_items_count=len(actionable_items),
            cost=result.total_cost,
        )

        return lesson

    def generate_improvements(
        self,
        pattern: FailurePattern,
        lesson: LearningLesson,
        current_prompts: Optional[Dict[str, str]] = None,
    ) -> ImprovementRecommendations:
        """Generate specific improvements using multi-agent consensus.

        Args:
            pattern: Original failure pattern
            lesson: Synthesized learning lesson
            current_prompts: Current prompt templates (if any)

        Returns:
            ImprovementRecommendations with specific changes
        """
        self.logger.info(
            "improvement_generation_started",
            pattern_id=pattern.pattern_id,
        )

        # Format current prompts
        prompts_text = ""
        if current_prompts:
            prompts_text = "\n\n".join(
                [
                    f"**{name}:**\n```\n{prompt}\n```"
                    for name, prompt in current_prompts.items()
                ]
            )
        else:
            prompts_text = "No existing prompts provided"

        # Create improvement generation prompt
        prompt = f"""Generate specific improvements to prevent this failure pattern:

**Failure Pattern:**
- Type: {pattern.failure_type}
- Error: {pattern.error_type}
- Occurrences: {pattern.occurrence_count}

**Lesson Learned:**
- Thesis: {lesson.thesis}
- Antithesis: {lesson.antithesis}
- Synthesis: {lesson.synthesis}
- Actionable Items: {json.dumps(lesson.actionable_items, indent=2)}

**Current Prompts:**
{prompts_text}

**Generate Specific Improvements:**

1. **Improved Prompt Templates:**
   - What should be added/changed in prompts?
   - Include specific wording and examples
   - Format as prompt template code

2. **Enhanced Validation Rules:**
   - What validation checks should be added?
   - What patterns should be detected?
   - Provide as code or pseudocode

3. **Better Complexity Estimation:**
   - How to better assess complexity for this type of task?
   - What factors were missed?
   - Suggested adjustments to scoring

4. **Additional Context:**
   - What context would have prevented this?
   - What examples should be included in prompts?
   - What warnings or caveats?

Build consensus on most effective improvements.
Provide concrete, implementable suggestions.
"""

        # Execute with ALL strategy for diverse perspectives
        result = self.multi_agent_client.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.ALL,
        )

        # Parse improvements from responses
        prompt_improvements = {}
        validation_rules = []
        complexity_adjustments = {}
        context_additions = []

        for response in result.responses:
            parsed = self._parse_improvements(response.content)
            prompt_improvements.update(parsed.get("prompts", {}))
            validation_rules.extend(parsed.get("validation", []))
            complexity_adjustments.update(parsed.get("complexity", {}))
            context_additions.extend(parsed.get("context", []))

        # Calculate consensus score
        consensus_score = self._calculate_consensus_confidence(
            {r.provider: r.content for r in result.responses}
        )

        recommendations = ImprovementRecommendations(
            pattern_id=pattern.pattern_id,
            prompt_improvements=prompt_improvements,
            validation_rules=list(set(validation_rules)),  # Remove duplicates
            complexity_adjustments=complexity_adjustments,
            context_additions=list(set(context_additions)),
            consensus_score=consensus_score,
            cost=result.total_cost,
            tokens_used=result.total_tokens,
        )

        self.logger.info(
            "improvement_generation_completed",
            pattern_id=pattern.pattern_id,
            prompt_improvements=len(prompt_improvements),
            validation_rules=len(validation_rules),
            cost=result.total_cost,
        )

        return recommendations

    def validate_effectiveness(
        self,
        pattern_id: str,
        improvements_applied: Dict[str, Any],
        metrics_before: Dict[str, float],
        metrics_after: Dict[str, float],
    ) -> EffectivenessValidation:
        """Validate effectiveness of applied improvements.

        Args:
            pattern_id: Pattern identifier
            improvements_applied: Description of what was changed
            metrics_before: Metrics before improvements
            metrics_after: Metrics after improvements

        Returns:
            EffectivenessValidation with recommendations
        """
        self.logger.info(
            "effectiveness_validation_started",
            pattern_id=pattern_id,
        )

        # Create validation prompt
        prompt = f"""Validate the effectiveness of improvements applied to address a failure pattern:

**Pattern ID:** {pattern_id}

**Improvements Applied:**
{json.dumps(improvements_applied, indent=2)}

**Metrics Before Improvements:**
{json.dumps(metrics_before, indent=2)}

**Metrics After Improvements:**
{json.dumps(metrics_after, indent=2)}

**Evaluation Questions:**
1. Did the improvements prevent similar failures?
2. What is the failure rate change (before vs after)?
3. Are there any unintended side effects or new issues?
4. Should we keep, refine, or revert these improvements?
5. What additional improvements could be made?
6. What else can we learn from this intervention?

**Provide Recommendation:**
- "keep": Improvements are effective, keep them
- "refine": Improvements partially work, need refinement
- "revert": Improvements caused problems, revert them

Build consensus on the learning success and next steps.
"""

        # Execute with DIALECTICAL strategy for thorough evaluation
        result = self.multi_agent_client.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.DIALECTICAL,
        )

        content = (
            result.summary
            if hasattr(result, "summary")
            else result.responses[0].content
        )

        # Parse results
        prevented_failures = (
            "prevented" in content.lower() or "success" in content.lower()
        )
        failure_rate_before = metrics_before.get("failure_rate", 0.0)
        failure_rate_after = metrics_after.get("failure_rate", 0.0)

        # Extract side effects
        side_effects = self._extract_side_effects(content)

        # Determine recommendation
        recommendation = self._extract_recommendation(content)

        # Calculate confidence
        confidence = self._calculate_consensus_confidence(
            {r.provider: r.content for r in result.responses}
        )

        validation = EffectivenessValidation(
            pattern_id=pattern_id,
            prevented_failures=prevented_failures,
            failure_rate_before=failure_rate_before,
            failure_rate_after=failure_rate_after,
            side_effects=side_effects,
            recommendation=recommendation,
            confidence=confidence,
            cost=result.total_cost,
            tokens_used=result.total_tokens,
        )

        self.logger.info(
            "effectiveness_validation_completed",
            pattern_id=pattern_id,
            recommendation=recommendation,
            confidence=confidence,
            cost=result.total_cost,
        )

        return validation

    # Helper methods

    def _format_failure_examples(self, failures: List[Dict[str, Any]]) -> str:
        """Format failure examples for prompt."""
        formatted = []
        for i, failure in enumerate(failures, 1):
            formatted.append(
                f"""
Example {i}:
- Operation ID: {failure.get('operation_id', 'N/A')}
- Error: {failure.get('error_message', 'N/A')}
- Retry Count: {failure.get('retry_count', 0)}
- Started: {failure.get('started_at', 'N/A')}
"""
            )
        return "\n".join(formatted)

    def _format_success_examples(self, successes: List[Dict[str, Any]]) -> str:
        """Format success examples for prompt."""
        if not successes:
            return "No successful examples available for comparison"

        formatted = []
        for i, success in enumerate(successes, 1):
            formatted.append(
                f"""
Success {i}:
- Operation ID: {success.get('operation_id', 'N/A')}
- Duration: {success.get('duration_seconds', 'N/A')} seconds
- Started: {success.get('started_at', 'N/A')}
"""
            )
        return "\n".join(formatted)

    def _calculate_consensus_confidence(self, analyses: Dict[str, str]) -> float:
        """Calculate confidence based on consensus among providers.

        Simple heuristic: more providers = higher baseline confidence.
        In reality, would analyze agreement in content.

        Args:
            analyses: Provider -> analysis mapping

        Returns:
            Confidence score 0.0-1.0
        """
        num_providers = len(analyses)
        if num_providers >= 4:
            return 0.9
        elif num_providers >= 3:
            return 0.8
        elif num_providers >= 2:
            return 0.7
        else:
            return 0.6

    def _extract_section(
        self, content: str, start_marker: str, end_marker: Optional[str]
    ) -> str:
        """Extract a section from dialectical response.

        Args:
            content: Full response content
            start_marker: Section start marker
            end_marker: Section end marker (None for last section)

        Returns:
            Extracted section text
        """
        start_idx = content.find(start_marker)
        if start_idx == -1:
            return ""

        start_idx += len(start_marker)

        if end_marker:
            end_idx = content.find(end_marker, start_idx)
            if end_idx == -1:
                return content[start_idx:].strip()
            return content[start_idx:end_idx].strip()
        else:
            return content[start_idx:].strip()

    def _extract_actionable_items(self, synthesis: str) -> List[str]:
        """Extract actionable items from synthesis text.

        Args:
            synthesis: Synthesis text

        Returns:
            List of actionable items
        """
        items = []
        lines = synthesis.split("\n")
        for line in lines:
            line = line.strip()
            # Look for bullet points or numbered lists
            if line.startswith(("-", "*", "•")) or (
                len(line) > 2 and line[0].isdigit() and line[1] in ".):"
            ):
                # Remove bullet/number
                item = line.lstrip("-*•123456789.): ").strip()
                if item and len(item) > 10:  # Meaningful length
                    items.append(item)
        return items[:10]  # Limit to 10 items

    def _parse_improvements(self, content: str) -> Dict[str, Any]:
        """Parse improvements from response content.

        Args:
            content: Response content

        Returns:
            Dictionary with parsed improvements
        """
        # Simplified parsing - in reality would be more sophisticated
        improvements = {
            "prompts": {},
            "validation": [],
            "complexity": {},
            "context": [],
        }

        # Look for prompt improvements
        if "prompt" in content.lower():
            improvements["prompts"]["default"] = content

        # Look for validation rules
        if "validation" in content.lower() or "check" in content.lower():
            improvements["validation"].append(content)

        # Look for complexity adjustments
        if "complexity" in content.lower():
            improvements["complexity"]["adjustment"] = "increase scrutiny"

        # Look for context additions
        if "context" in content.lower() or "example" in content.lower():
            improvements["context"].append(content)

        return improvements

    def _extract_side_effects(self, content: str) -> List[str]:
        """Extract side effects from validation content.

        Args:
            content: Validation response content

        Returns:
            List of identified side effects
        """
        side_effects = []
        content_lower = content.lower()

        if "side effect" in content_lower or "unintended" in content_lower:
            # Parse out mentions of side effects
            lines = content.split("\n")
            for line in lines:
                if "side effect" in line.lower() or "unintended" in line.lower():
                    side_effects.append(line.strip())

        return side_effects

    def _extract_recommendation(self, content: str) -> str:
        """Extract recommendation from validation content.

        Args:
            content: Validation response content

        Returns:
            Recommendation: "keep", "refine", or "revert"
        """
        content_lower = content.lower()

        if "revert" in content_lower:
            return "revert"
        elif "refine" in content_lower or "adjust" in content_lower:
            return "refine"
        elif "keep" in content_lower or "maintain" in content_lower:
            return "keep"
        else:
            # Default to keep if no clear recommendation
            return "keep"
