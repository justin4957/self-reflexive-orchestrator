"""Roadmap validator using dialectical multi-agent validation.

Validates roadmap proposals through three phases:
1. Thesis: Initial multi-agent analysis of proposals
2. Antithesis: Critical analysis and risk identification
3. Synthesis: Refined recommendations with consensus

This follows the dialectical method to ensure thorough validation
through multiple AI perspectives.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import re
import time

from ..cycles.multi_agent_ideation import (
    FeatureProposal,
    SynthesizedRoadmap,
    IdeationResult,
)
from ..integrations.multi_agent_coder_client import (
    MultiAgentCoderClient,
    MultiAgentStrategy,
    MultiAgentResponse,
)
from ..core.logger import AuditLogger


class ValidationDecision(Enum):
    """Validation decision for a proposal."""

    APPROVED = "approved"
    APPROVED_WITH_CHANGES = "approved_with_changes"
    NEEDS_REVISION = "needs_revision"
    REJECTED = "rejected"


class ValidationCriterion(Enum):
    """Validation criteria for roadmap proposals."""

    ALIGNMENT = "alignment"  # Aligns with project goals
    FEASIBILITY = "feasibility"  # Technically feasible
    PRIORITY = "priority"  # Important right now
    SCOPE = "scope"  # Appropriate scope
    DEPENDENCIES = "dependencies"  # No critical blockers
    VALUE = "value"  # Provides sufficient value


@dataclass
class ProposalValidation:
    """Validation result for a single proposal."""

    proposal_id: str
    decision: ValidationDecision
    confidence: float  # 0-1
    criteria_scores: Dict[ValidationCriterion, float] = field(
        default_factory=dict
    )  # criterion -> 0-1
    strengths: List[str] = field(default_factory=list)
    concerns: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    alternatives: List[str] = field(default_factory=list)
    provider_opinions: Dict[str, str] = field(
        default_factory=dict
    )  # provider -> opinion

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "proposal_id": self.proposal_id,
            "decision": self.decision.value,
            "confidence": self.confidence,
            "criteria_scores": {k.value: v for k, v in self.criteria_scores.items()},
            "strengths": self.strengths,
            "concerns": self.concerns,
            "risks": self.risks,
            "suggestions": self.suggestions,
            "alternatives": self.alternatives,
            "provider_opinions": self.provider_opinions,
        }


@dataclass
class DialecticalValidation:
    """Results from dialectical validation process."""

    thesis: str  # Initial analysis
    antithesis: str  # Critical analysis
    synthesis: str  # Refined recommendations
    consensus_confidence: float  # 0-1
    total_cost: float
    total_tokens: int
    duration_seconds: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "thesis": self.thesis,
            "antithesis": self.antithesis,
            "synthesis": self.synthesis,
            "consensus_confidence": self.consensus_confidence,
            "total_cost": self.total_cost,
            "total_tokens": self.total_tokens,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class ValidatedRoadmap:
    """Validated roadmap with refined proposals."""

    original_roadmap: SynthesizedRoadmap
    validated_proposals: Dict[str, ProposalValidation]  # proposal_id -> validation
    dialectical_validation: DialecticalValidation
    approved_proposals: List[FeatureProposal]
    rejected_proposals: List[FeatureProposal]
    needs_revision: List[FeatureProposal]
    refined_phases: List[Dict[str, Any]]
    overall_confidence: float  # 0-1
    total_cost: float
    total_tokens: int
    duration_seconds: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "original_roadmap": self.original_roadmap.to_dict(),
            "validated_proposals": {
                k: v.to_dict() for k, v in self.validated_proposals.items()
            },
            "dialectical_validation": self.dialectical_validation.to_dict(),
            "approved_proposals": [p.to_dict() for p in self.approved_proposals],
            "rejected_proposals": [p.to_dict() for p in self.rejected_proposals],
            "needs_revision": [p.to_dict() for p in self.needs_revision],
            "refined_phases": self.refined_phases,
            "overall_confidence": self.overall_confidence,
            "total_cost": self.total_cost,
            "total_tokens": self.total_tokens,
            "duration_seconds": self.duration_seconds,
        }


class RoadmapValidator:
    """Validates roadmaps using dialectical multi-agent analysis.

    Responsibilities:
    - Phase 1 (Thesis): Initial multi-agent analysis of proposals
    - Phase 2 (Antithesis): Critical analysis identifying concerns/risks
    - Phase 3 (Synthesis): Refined recommendations with consensus
    - Parse validation results and decisions
    - Filter proposals based on validation
    - Generate refined roadmap with validated features
    - Log validation process with confidence scores
    """

    # Validation criteria keywords for parsing
    CRITERIA_KEYWORDS = {
        ValidationCriterion.ALIGNMENT: ["align", "goal", "objective", "mission"],
        ValidationCriterion.FEASIBILITY: [
            "feasible",
            "implement",
            "technical",
            "viable",
        ],
        ValidationCriterion.PRIORITY: ["priority", "urgent", "important", "critical"],
        ValidationCriterion.SCOPE: ["scope", "size", "effort", "complexity"],
        ValidationCriterion.DEPENDENCIES: [
            "depend",
            "block",
            "prerequisite",
            "require",
        ],
        ValidationCriterion.VALUE: ["value", "impact", "benefit", "roi"],
    }

    def __init__(
        self,
        multi_agent_client: MultiAgentCoderClient,
        logger: AuditLogger,
        min_confidence: float = 0.8,
    ):
        """Initialize roadmap validator.

        Args:
            multi_agent_client: Multi-agent-coder client
            logger: Audit logger
            min_confidence: Minimum confidence threshold for approval (default 0.8)
        """
        self.multi_agent_client = multi_agent_client
        self.logger = logger
        self.min_confidence = min_confidence

    def validate_roadmap(
        self,
        ideation_result: IdeationResult,
        project_goals: Optional[List[str]] = None,
    ) -> ValidatedRoadmap:
        """Validate roadmap through dialectical multi-agent analysis.

        Args:
            ideation_result: Results from roadmap ideation
            project_goals: Optional project goals for validation context

        Returns:
            ValidatedRoadmap with refined proposals and validation results
        """
        start_time = time.time()
        total_cost = 0.0
        total_tokens = 0

        self.logger.info(
            "roadmap_validation_started",
            proposals_count=len(ideation_result.proposals),
            min_confidence=self.min_confidence,
        )

        # Phase 1: THESIS - Initial multi-agent analysis
        self.logger.info("validation_phase_1_thesis", phase="initial_analysis")
        thesis_response = self._phase_1_thesis(
            ideation_result.proposals,
            ideation_result.synthesized_roadmap,
            project_goals,
        )
        total_cost += thesis_response.total_cost
        total_tokens += thesis_response.total_tokens

        # Phase 2: ANTITHESIS - Critical analysis
        self.logger.info("validation_phase_2_antithesis", phase="critical_analysis")
        antithesis_response = self._phase_2_antithesis(
            ideation_result.proposals, thesis_response
        )
        total_cost += antithesis_response.total_cost
        total_tokens += antithesis_response.total_tokens

        # Phase 3: SYNTHESIS - Refined recommendations
        self.logger.info(
            "validation_phase_3_synthesis", phase="refined_recommendations"
        )
        synthesis_response = self._phase_3_synthesis(
            thesis_response, antithesis_response
        )
        total_cost += synthesis_response.total_cost
        total_tokens += synthesis_response.total_tokens

        # Create dialectical validation record
        duration = time.time() - start_time
        dialectical_validation = DialecticalValidation(
            thesis=self._extract_combined_response(thesis_response),
            antithesis=self._extract_combined_response(antithesis_response),
            synthesis=self._extract_combined_response(synthesis_response),
            consensus_confidence=self._calculate_consensus_confidence(
                synthesis_response
            ),
            total_cost=total_cost,
            total_tokens=total_tokens,
            duration_seconds=duration,
        )

        # Parse validation results
        validated_proposals = self._parse_validation_results(
            ideation_result.proposals, synthesis_response
        )

        # Categorize proposals
        approved = []
        rejected = []
        needs_revision = []

        proposal_map = {p.id: p for p in ideation_result.proposals}

        for proposal_id, validation in validated_proposals.items():
            proposal = proposal_map.get(proposal_id)
            if not proposal:
                continue

            if validation.decision == ValidationDecision.APPROVED:
                approved.append(proposal)
            elif validation.decision == ValidationDecision.APPROVED_WITH_CHANGES:
                approved.append(proposal)
            elif validation.decision == ValidationDecision.NEEDS_REVISION:
                needs_revision.append(proposal)
            elif validation.decision == ValidationDecision.REJECTED:
                rejected.append(proposal)

        # Generate refined phases
        refined_phases = self._generate_refined_phases(
            approved, ideation_result.synthesized_roadmap.phases
        )

        # Calculate overall confidence
        overall_confidence = self._calculate_overall_confidence(
            validated_proposals, dialectical_validation.consensus_confidence
        )

        self.logger.info(
            "roadmap_validation_completed",
            approved_count=len(approved),
            rejected_count=len(rejected),
            needs_revision_count=len(needs_revision),
            overall_confidence=overall_confidence,
            total_cost=total_cost,
            duration_seconds=duration,
        )

        return ValidatedRoadmap(
            original_roadmap=ideation_result.synthesized_roadmap,
            validated_proposals=validated_proposals,
            dialectical_validation=dialectical_validation,
            approved_proposals=approved,
            rejected_proposals=rejected,
            needs_revision=needs_revision,
            refined_phases=refined_phases,
            overall_confidence=overall_confidence,
            total_cost=total_cost,
            total_tokens=total_tokens,
            duration_seconds=duration,
        )

    def _phase_1_thesis(
        self,
        proposals: List[FeatureProposal],
        roadmap: SynthesizedRoadmap,
        project_goals: Optional[List[str]],
    ) -> MultiAgentResponse:
        """Phase 1: THESIS - Initial multi-agent analysis.

        All providers independently evaluate proposals.
        """
        # Format proposals for analysis
        proposals_text = self._format_proposals_for_validation(proposals)

        # Build context
        context_parts = [
            "# Roadmap Validation - Initial Analysis\n",
            "## Project Goals\n",
        ]

        if project_goals:
            for i, goal in enumerate(project_goals, 1):
                context_parts.append(f"{i}. {goal}\n")
        else:
            context_parts.append("No specific goals provided.\n")

        context_parts.extend(
            [
                "\n## Roadmap Proposals\n",
                proposals_text,
                "\n## Validation Criteria\n",
                "Evaluate each proposal on:\n",
                f"1. **Alignment**: Does it align with project goals?\n",
                f"2. **Feasibility**: Is it technically feasible?\n",
                f"3. **Priority**: Is it important right now?\n",
                f"4. **Scope**: Is the scope appropriate?\n",
                f"5. **Dependencies**: Are there blockers?\n",
                f"6. **Value**: Does it provide sufficient value?\n",
                "\nFor each proposal, provide:\n",
                "- Overall assessment (Approve/Approve with changes/Needs revision/Reject)\n",
                "- Scores for each criterion (0-1)\n",
                "- Key strengths\n",
                "- Potential concerns\n",
            ]
        )

        prompt = "".join(context_parts)

        # Query all providers for initial analysis
        return self.multi_agent_client.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.ALL,
        )

    def _phase_2_antithesis(
        self, proposals: List[FeatureProposal], thesis: MultiAgentResponse
    ) -> MultiAgentResponse:
        """Phase 2: ANTITHESIS - Critical analysis.

        Use dialectical strategy to identify concerns, risks, and alternatives.
        """
        proposals_text = self._format_proposals_for_validation(proposals)
        thesis_text = self._extract_combined_response(thesis)

        prompt = f"""# Roadmap Validation - Critical Analysis

## Proposals
{proposals_text}

## Initial Analysis (Thesis)
{thesis_text}

## Critical Evaluation

Your role is to provide critical analysis to ensure we don't overlook important concerns.

For each proposal, identify:
1. **Concerns**: What could go wrong?
2. **Risks**: Technical, timeline, or resource risks
3. **Alternatives**: Are there better approaches?
4. **Hidden Costs**: Maintenance burden, technical debt, etc.
5. **Dependencies**: Critical blockers or prerequisites

Be thorough and constructive. The goal is to refine proposals, not just criticize.
"""

        # Use dialectical strategy for deeper analysis
        return self.multi_agent_client.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.DIALECTICAL,
        )

    def _phase_3_synthesis(
        self, thesis: MultiAgentResponse, antithesis: MultiAgentResponse
    ) -> MultiAgentResponse:
        """Phase 3: SYNTHESIS - Refined recommendations.

        Synthesize thesis and antithesis into balanced recommendations.
        """
        thesis_text = self._extract_combined_response(thesis)
        antithesis_text = self._extract_combined_response(antithesis)

        prompt = f"""# Roadmap Validation - Synthesis

## Thesis (Initial Analysis)
{thesis_text}

## Antithesis (Critical Analysis)
{antithesis_text}

## Synthesis Task

Provide refined, balanced recommendations that:
1. Incorporate insights from both thesis and antithesis
2. Balance optimism with pragmatism
3. Provide clear decisions for each proposal

For each proposal, provide:
- **Decision**: APPROVED | APPROVED_WITH_CHANGES | NEEDS_REVISION | REJECTED
- **Confidence**: 0.0-1.0 (how confident in this decision)
- **Rationale**: Brief explanation
- **Suggestions**: Specific improvements if approved with changes or needs revision

Format each proposal assessment as:

---
**Proposal ID**: <id>
**Decision**: <decision>
**Confidence**: <0.0-1.0>
**Rationale**: <explanation>
**Suggestions**: <improvements>
---
"""

        # Use dialectical strategy for synthesis
        return self.multi_agent_client.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.DIALECTICAL,
        )

    def _format_proposals_for_validation(self, proposals: List[FeatureProposal]) -> str:
        """Format proposals for validation."""
        lines = []

        for proposal in proposals:
            lines.extend(
                [
                    f"\n### Proposal {proposal.id}\n",
                    f"**Title**: {proposal.title}\n",
                    f"**Provider**: {proposal.provider.upper()}\n",
                    f"**Priority**: {proposal.priority.value.upper()}\n",
                    f"**Complexity**: {proposal.complexity_estimate}/10\n",
                    f"\n**Description**:\n{proposal.description}\n",
                    f"\n**Value Proposition**:\n{proposal.value_proposition}\n",
                ]
            )

            if proposal.estimated_effort:
                lines.append(f"\n**Estimated Effort**: {proposal.estimated_effort}\n")

            if proposal.dependencies:
                lines.append(
                    f"\n**Dependencies**: {', '.join(proposal.dependencies)}\n"
                )

            if proposal.success_metrics:
                lines.append("\n**Success Metrics**:\n")
                for metric in proposal.success_metrics:
                    lines.append(f"- {metric}\n")

        return "".join(lines)

    def _extract_combined_response(self, response: MultiAgentResponse) -> str:
        """Extract combined text from multi-agent response."""
        if not response.responses:
            return ""

        lines = []
        for provider, text in response.responses.items():
            lines.extend([f"\n## {provider.upper()}\n", text, "\n"])

        return "".join(lines)

    def _calculate_consensus_confidence(self, response: MultiAgentResponse) -> float:
        """Calculate consensus confidence from synthesis response."""
        # Extract confidence scores from text
        text = self._extract_combined_response(response)
        confidence_pattern = r"[Cc]onfidence[:\s]+([0-9.]+)"

        matches = re.findall(confidence_pattern, text)
        if matches:
            scores = [float(m) for m in matches if float(m) <= 1.0]
            if scores:
                return sum(scores) / len(scores)

        # Default to moderate confidence if no explicit scores
        return 0.75

    def _parse_validation_results(
        self, proposals: List[FeatureProposal], synthesis: MultiAgentResponse
    ) -> Dict[str, ProposalValidation]:
        """Parse validation results from synthesis response."""
        text = self._extract_combined_response(synthesis)
        validations = {}

        # Parse each proposal's validation
        for proposal in proposals:
            validation = self._parse_proposal_validation(proposal, text)
            validations[proposal.id] = validation

        return validations

    def _parse_proposal_validation(
        self, proposal: FeatureProposal, synthesis_text: str
    ) -> ProposalValidation:
        """Parse validation for a single proposal."""
        # Find section for this proposal
        proposal_pattern = (
            rf"Proposal[:\s]+{re.escape(proposal.id)}(.*?)(?=Proposal[:\s]+\w+|\Z)"
        )
        match = re.search(proposal_pattern, synthesis_text, re.DOTALL | re.IGNORECASE)

        if not match:
            # No explicit validation found, default to approved with moderate confidence
            return ProposalValidation(
                proposal_id=proposal.id,
                decision=ValidationDecision.APPROVED,
                confidence=0.7,
            )

        section = match.group(1)

        # Extract decision
        decision = self._extract_decision(section)

        # Extract confidence
        confidence = self._extract_confidence(section)

        # Extract criteria scores
        criteria_scores = self._extract_criteria_scores(section)

        # Extract strengths, concerns, risks
        strengths = self._extract_list_items(section, "strength")
        concerns = self._extract_list_items(section, "concern")
        risks = self._extract_list_items(section, "risk")
        suggestions = self._extract_list_items(section, "suggestion")
        alternatives = self._extract_list_items(section, "alternative")

        return ProposalValidation(
            proposal_id=proposal.id,
            decision=decision,
            confidence=confidence,
            criteria_scores=criteria_scores,
            strengths=strengths,
            concerns=concerns,
            risks=risks,
            suggestions=suggestions,
            alternatives=alternatives,
        )

    def _extract_decision(self, text: str) -> ValidationDecision:
        """Extract validation decision from text."""
        text_lower = text.lower()

        if "rejected" in text_lower or "reject" in text_lower:
            return ValidationDecision.REJECTED
        elif "needs revision" in text_lower or "needs_revision" in text_lower:
            return ValidationDecision.NEEDS_REVISION
        elif (
            "approved with changes" in text_lower
            or "approved_with_changes" in text_lower
        ):
            return ValidationDecision.APPROVED_WITH_CHANGES
        elif "approved" in text_lower or "approve" in text_lower:
            return ValidationDecision.APPROVED

        # Default to approved if unclear
        return ValidationDecision.APPROVED

    def _extract_confidence(self, text: str) -> float:
        """Extract confidence score from text."""
        pattern = r"[Cc]onfidence[:\s]+([0-9.]+)"
        match = re.search(pattern, text)

        if match:
            score = float(match.group(1))
            # Ensure 0-1 range
            if score <= 1.0:
                return score
            elif score <= 10.0:
                return score / 10.0
            elif score <= 100.0:
                return score / 100.0

        # Default to moderate confidence
        return 0.75

    def _extract_criteria_scores(self, text: str) -> Dict[ValidationCriterion, float]:
        """Extract criteria scores from text."""
        scores = {}

        for criterion, keywords in self.CRITERIA_KEYWORDS.items():
            # Look for scores near keywords
            for keyword in keywords:
                pattern = rf"{keyword}[:\s]+([0-9.]+)"
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    score = float(match.group(1))
                    if score <= 1.0:
                        scores[criterion] = score
                        break
                    elif score <= 10.0:
                        scores[criterion] = score / 10.0
                        break

        return scores

    def _extract_list_items(self, text: str, category: str) -> List[str]:
        """Extract list items for a category (strengths, concerns, etc.)."""
        items = []

        # Look for section header
        pattern = rf"{category}[s]?[:\s]+(.*?)(?=[A-Z][a-z]+:|$)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)

        if match:
            content = match.group(1)
            # Extract bullet points or numbered items
            bullet_pattern = r"[-*•]\s*(.+?)(?=\n[-*•]|\n\n|\Z)"
            items.extend(re.findall(bullet_pattern, content, re.DOTALL))

        return [item.strip() for item in items if item.strip()]

    def _generate_refined_phases(
        self,
        approved_proposals: List[FeatureProposal],
        original_phases: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Generate refined phases with only approved proposals."""
        # Map proposal IDs to proposals
        approved_ids = {p.id for p in approved_proposals}

        refined_phases = []
        for phase in original_phases:
            # Filter features to only approved ones
            original_features = phase.get("features", [])
            refined_features = [
                f for f in original_features if f.get("id") in approved_ids
            ]

            # Only include phase if it has approved features
            if refined_features:
                refined_phase = phase.copy()
                refined_phase["features"] = refined_features
                refined_phases.append(refined_phase)

        return refined_phases

    def _calculate_overall_confidence(
        self,
        validated_proposals: Dict[str, ProposalValidation],
        dialectical_confidence: float,
    ) -> float:
        """Calculate overall validation confidence."""
        if not validated_proposals:
            return dialectical_confidence

        # Average of individual proposal confidences
        proposal_confidences = [v.confidence for v in validated_proposals.values()]
        avg_proposal_confidence = sum(proposal_confidences) / len(proposal_confidences)

        # Weight: 60% dialectical consensus, 40% individual proposals
        return 0.6 * dialectical_confidence + 0.4 * avg_proposal_confidence
