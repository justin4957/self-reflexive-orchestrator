"""Multi-agent ideation for roadmap generation.

Uses multiple AI providers to generate diverse feature proposals,
cross-critique ideas, and build consensus through dialectical synthesis.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from ..integrations.multi_agent_coder_client import (
    MultiAgentCoderClient,
    MultiAgentStrategy,
    MultiAgentResponse,
)
from ..analyzers.codebase_analyzer import CodebaseAnalysis
from ..analyzers.multi_agent_analyzer import MultiAgentAnalysisResult
from ..core.logger import AuditLogger


class ProposalPriority(Enum):
    """Priority levels for feature proposals."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class FeatureProposal:
    """A single feature proposal from an AI provider."""

    id: str
    title: str
    description: str
    provider: str
    value_proposition: str
    complexity_estimate: int  # 1-10
    priority: ProposalPriority
    dependencies: List[str] = field(default_factory=list)
    success_metrics: List[str] = field(default_factory=list)
    estimated_effort: Optional[str] = None  # e.g., "2-3 weeks"
    category: Optional[str] = None  # e.g., "performance", "ux", "security"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "provider": self.provider,
            "value_proposition": self.value_proposition,
            "complexity_estimate": self.complexity_estimate,
            "priority": self.priority.value,
            "dependencies": self.dependencies,
            "success_metrics": self.success_metrics,
            "estimated_effort": self.estimated_effort,
            "category": self.category,
        }


@dataclass
class ProposalCritique:
    """Critique of a proposal from multiple perspectives."""

    proposal_id: str
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    feasibility_score: float = 0.0  # 0-1
    value_score: float = 0.0  # 0-1
    overlaps_with: List[str] = field(default_factory=list)
    conflicts_with: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    provider_ratings: Dict[str, int] = field(default_factory=dict)  # provider -> 1-10

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "proposal_id": self.proposal_id,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "feasibility_score": self.feasibility_score,
            "value_score": self.value_score,
            "overlaps_with": self.overlaps_with,
            "conflicts_with": self.conflicts_with,
            "suggestions": self.suggestions,
            "provider_ratings": self.provider_ratings,
        }


@dataclass
class SynthesizedRoadmap:
    """Synthesized roadmap from multi-agent ideation."""

    phases: List[Dict[str, Any]]  # [{name, timeline, features}]
    consensus_confidence: float  # 0-1
    total_proposals_considered: int
    selected_proposals: int
    provider_perspectives: Dict[str, str]  # provider -> key emphasis
    synthesis_notes: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "phases": self.phases,
            "consensus_confidence": self.consensus_confidence,
            "total_proposals_considered": self.total_proposals_considered,
            "selected_proposals": self.selected_proposals,
            "provider_perspectives": self.provider_perspectives,
            "synthesis_notes": self.synthesis_notes,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class IdeationResult:
    """Complete result of multi-agent ideation process."""

    proposals: List[FeatureProposal]
    critiques: Dict[str, ProposalCritique]  # proposal_id -> critique
    synthesized_roadmap: SynthesizedRoadmap
    total_cost: float
    total_tokens: int
    duration_seconds: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "proposals": [p.to_dict() for p in self.proposals],
            "critiques": {k: v.to_dict() for k, v in self.critiques.items()},
            "synthesized_roadmap": self.synthesized_roadmap.to_dict(),
            "total_cost": self.total_cost,
            "total_tokens": self.total_tokens,
            "duration_seconds": self.duration_seconds,
        }


class MultiAgentIdeation:
    """Multi-agent ideation engine for roadmap generation.

    Responsibilities:
    - Coordinate parallel ideation across multiple AI providers
    - Each AI generates proposals from their specialized perspective
    - Cross-critique proposals to identify strengths, weaknesses, overlaps
    - Synthesize best ideas through dialectical method
    - Build consensus roadmap with clear phases and priorities
    """

    # Provider focus areas (from multi_agent_analyzer.py)
    PROVIDER_FOCUS = {
        "anthropic": "Enterprise features, security, and scalability",
        "deepseek": "Performance optimization and resource efficiency",
        "openai": "User experience and innovative features",
        "perplexity": "Industry best practices and standards compliance",
    }

    def __init__(
        self,
        multi_agent_client: MultiAgentCoderClient,
        logger: AuditLogger,
    ):
        """Initialize multi-agent ideation engine.

        Args:
            multi_agent_client: Multi-agent-coder client
            logger: Audit logger
        """
        self.multi_agent_client = multi_agent_client
        self.logger = logger

    def generate_roadmap(
        self,
        codebase_analysis: CodebaseAnalysis,
        multi_agent_analysis: MultiAgentAnalysisResult,
        project_goals: Optional[List[str]] = None,
    ) -> IdeationResult:
        """Generate roadmap through multi-agent ideation.

        Args:
            codebase_analysis: Raw codebase analysis
            multi_agent_analysis: Multi-agent insights on codebase
            project_goals: Optional list of specific project goals

        Returns:
            IdeationResult with proposals, critiques, and synthesized roadmap
        """
        start_time = datetime.now(timezone.utc)

        self.logger.info(
            "Starting multi-agent roadmap ideation",
            project_goals=project_goals,
        )

        # Phase 1: Parallel ideation
        proposals = self._parallel_ideation(
            codebase_analysis, multi_agent_analysis, project_goals
        )

        # Phase 2: Cross-critique
        critiques = self._cross_critique(proposals)

        # Phase 3: Dialectical synthesis
        synthesized_roadmap = self._dialectical_synthesis(proposals, critiques)

        # Calculate metrics
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        # Get cost/token stats from multi_agent_client
        stats = self.multi_agent_client.get_statistics()

        result = IdeationResult(
            proposals=proposals,
            critiques=critiques,
            synthesized_roadmap=synthesized_roadmap,
            total_cost=stats.get("total_cost", 0.0),
            total_tokens=stats.get("total_tokens", 0),
            duration_seconds=duration,
        )

        self.logger.info(
            "Multi-agent roadmap ideation complete",
            total_proposals=len(proposals),
            selected_proposals=synthesized_roadmap.selected_proposals,
            consensus_confidence=synthesized_roadmap.consensus_confidence,
            duration_seconds=duration,
            total_cost=stats.get("total_cost", 0.0),
        )

        return result

    def _parallel_ideation(
        self,
        codebase_analysis: CodebaseAnalysis,
        multi_agent_analysis: MultiAgentAnalysisResult,
        project_goals: Optional[List[str]],
    ) -> List[FeatureProposal]:
        """Phase 1: Parallel ideation from multiple AI perspectives.

        Args:
            codebase_analysis: Raw codebase analysis
            multi_agent_analysis: Multi-agent insights
            project_goals: Optional project goals

        Returns:
            List of feature proposals from all providers
        """
        self.logger.info("Phase 1: Parallel ideation from all providers")

        # Build context for ideation
        context = self._build_ideation_context(
            codebase_analysis, multi_agent_analysis, project_goals
        )

        # Query all providers in parallel
        prompt = f"""Based on this codebase analysis and insights, propose 5-8 features for the next development phase.

{context}

**Your Focus**: {self.PROVIDER_FOCUS.get('your_provider', 'General software development')}

For each proposal, provide:
1. **Title**: Clear, concise feature name
2. **Description**: What the feature does and why it matters
3. **Value Proposition**: Business/technical value delivered
4. **Complexity**: Estimate 1-10 (1=trivial, 10=extremely complex)
5. **Priority**: CRITICAL, HIGH, MEDIUM, or LOW
6. **Dependencies**: What must exist first
7. **Success Metrics**: How to measure success
8. **Estimated Effort**: Rough timeline (e.g., "1-2 weeks", "2-3 months")
9. **Category**: Type (performance, ux, security, feature, debt, etc.)

Focus on actionable, high-value features that align with your expertise.
"""

        response = self.multi_agent_client.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.ALL,
            timeout=180,
        )

        # Parse proposals from each provider
        proposals = []
        for provider, provider_response in response.responses.items():
            provider_proposals = self._parse_proposals(provider, provider_response)
            proposals.extend(provider_proposals)

        self.logger.info(
            f"Generated {len(proposals)} proposals from {len(response.providers)} providers"
        )

        return proposals

    def _cross_critique(
        self, proposals: List[FeatureProposal]
    ) -> Dict[str, ProposalCritique]:
        """Phase 2: Cross-critique all proposals.

        Args:
            proposals: List of feature proposals

        Returns:
            Dictionary mapping proposal_id to critique
        """
        self.logger.info(f"Phase 2: Cross-critique of {len(proposals)} proposals")

        # Format proposals for critique
        proposals_text = self._format_proposals_for_critique(proposals)

        prompt = f"""Review and critique these feature proposals from multiple AI perspectives:

{proposals_text}

For each proposal, analyze:

1. **Strengths**: What makes this proposal valuable?
2. **Weaknesses**: What are the concerns or risks?
3. **Feasibility**: Rate 0-1 (0=not feasible, 1=very feasible)
4. **Value**: Rate 0-1 (0=low value, 1=high value)
5. **Overlaps**: Which other proposals address similar goals?
6. **Conflicts**: Which proposals compete or conflict?
7. **Suggestions**: How to improve this proposal?
8. **Rating**: Your overall rating 1-10

Identify the top 10-15 proposals that should be included in the roadmap.
Consider balance across categories (performance, UX, security, features).
"""

        response = self.multi_agent_client.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.ALL,
            timeout=240,
        )

        # Parse critiques
        critiques = self._parse_critiques(proposals, response)

        self.logger.info(f"Completed critique analysis for {len(critiques)} proposals")

        return critiques

    def _dialectical_synthesis(
        self,
        proposals: List[FeatureProposal],
        critiques: Dict[str, ProposalCritique],
    ) -> SynthesizedRoadmap:
        """Phase 3: Synthesize proposals into cohesive roadmap.

        Args:
            proposals: All feature proposals
            critiques: Critiques for each proposal

        Returns:
            Synthesized roadmap with phases
        """
        self.logger.info("Phase 3: Dialectical synthesis into roadmap")

        # Filter proposals by critique scores
        viable_proposals = self._filter_viable_proposals(proposals, critiques)

        # Format for synthesis
        synthesis_input = self._format_for_synthesis(viable_proposals, critiques)

        prompt = f"""Synthesize these feature proposals and critiques into a cohesive development roadmap.

{synthesis_input}

Create a roadmap with 3-4 phases:

**Phase 1: Foundation (Immediate - 4-8 weeks)**
- Critical fixes and foundational improvements
- High-value, lower-risk features
- 3-5 key features

**Phase 2: Enhancement (Short-term - 2-3 months)**
- Medium-complexity features
- User-facing improvements
- 4-6 key features

**Phase 3: Innovation (Medium-term - 3-6 months)**
- Higher-complexity features
- Strategic improvements
- 3-5 key features

**Phase 4: Evolution (Long-term - 6+ months)** (optional)
- Advanced features
- Scaling and optimization
- 2-4 key features

For each phase:
- Select features that work well together
- Resolve dependencies and conflicts
- Balance across categories (performance, UX, security, features)
- Provide clear rationale for selection
- Include timeline and success metrics

Build consensus across all AI perspectives. Note key emphases from each provider.
Calculate overall consensus confidence (0-1).
"""

        response = self.multi_agent_client.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.DIALECTICAL,
            timeout=300,
        )

        # Parse synthesized roadmap
        synthesized_roadmap = self._parse_synthesized_roadmap(
            response, proposals, critiques
        )

        self.logger.info(
            f"Synthesized roadmap with {len(synthesized_roadmap.phases)} phases, "
            f"{synthesized_roadmap.selected_proposals} features, "
            f"confidence: {synthesized_roadmap.consensus_confidence:.2f}"
        )

        return synthesized_roadmap

    def _build_ideation_context(
        self,
        codebase_analysis: CodebaseAnalysis,
        multi_agent_analysis: MultiAgentAnalysisResult,
        project_goals: Optional[List[str]],
    ) -> str:
        """Build context for ideation prompt.

        Args:
            codebase_analysis: Raw codebase analysis
            multi_agent_analysis: Multi-agent insights
            project_goals: Optional project goals

        Returns:
            Formatted context string
        """
        metrics = codebase_analysis.metrics
        consensus = multi_agent_analysis.consensus

        context_parts = [
            "**Codebase Overview:**",
            f"- Total Files: {metrics.total_files}",
            f"- Lines of Code: {metrics.total_code_lines:,}",
            f"- Languages: {', '.join(metrics.languages.keys())}",
            f"- Average Complexity: {metrics.avg_complexity:.1f}",
            f"- Architecture: {codebase_analysis.patterns.get('architecture_pattern', 'Unknown')}",
            "",
            "**Current State (Multi-Agent Analysis):**",
            f"- Architecture Rating: {consensus.overall_architecture_rating:.1f}/10",
            f"- Quality Rating: {consensus.overall_quality_rating:.1f}/10",
            f"- Consensus Confidence: {consensus.consensus_confidence:.1%}",
        ]

        # Add top priorities
        if consensus.top_priorities:
            context_parts.append("")
            context_parts.append("**Top Priorities Identified:**")
            for i, priority in enumerate(consensus.top_priorities[:5], 1):
                context_parts.append(
                    f"{i}. [{priority['priority'].upper()}] {priority['description']}"
                )

        # Add project goals if provided
        if project_goals:
            context_parts.append("")
            context_parts.append("**Project Goals:**")
            for goal in project_goals:
                context_parts.append(f"- {goal}")

        return "\n".join(context_parts)

    def _format_proposals_for_critique(self, proposals: List[FeatureProposal]) -> str:
        """Format proposals for critique prompt.

        Args:
            proposals: List of proposals

        Returns:
            Formatted string
        """
        lines = []
        for proposal in proposals:
            lines.append(f"**{proposal.id}: {proposal.title}**")
            lines.append(f"Provider: {proposal.provider}")
            lines.append(f"Description: {proposal.description}")
            lines.append(f"Value: {proposal.value_proposition}")
            lines.append(f"Complexity: {proposal.complexity_estimate}/10")
            lines.append(f"Priority: {proposal.priority.value}")
            if proposal.category:
                lines.append(f"Category: {proposal.category}")
            lines.append("")

        return "\n".join(lines)

    def _format_for_synthesis(
        self,
        proposals: List[FeatureProposal],
        critiques: Dict[str, ProposalCritique],
    ) -> str:
        """Format proposals and critiques for synthesis.

        Args:
            proposals: Viable proposals
            critiques: Critiques for proposals

        Returns:
            Formatted string
        """
        lines = []
        for proposal in proposals:
            critique = critiques.get(proposal.id)
            if not critique:
                continue

            lines.append(f"**{proposal.id}: {proposal.title}**")
            lines.append(f"- Provider: {proposal.provider}")
            lines.append(f"- Description: {proposal.description}")
            lines.append(f"- Value: {proposal.value_proposition}")
            lines.append(f"- Complexity: {proposal.complexity_estimate}/10")
            lines.append(f"- Priority: {proposal.priority.value}")
            lines.append(f"- Feasibility Score: {critique.feasibility_score:.2f}")
            lines.append(f"- Value Score: {critique.value_score:.2f}")
            if critique.strengths:
                lines.append(f"- Strengths: {', '.join(critique.strengths[:2])}")
            if critique.overlaps_with:
                lines.append(f"- Overlaps: {', '.join(critique.overlaps_with[:2])}")
            lines.append("")

        return "\n".join(lines)

    def _parse_proposals(
        self, provider: str, response_text: str
    ) -> List[FeatureProposal]:
        """Parse proposals from provider response.

        Args:
            provider: Provider name
            response_text: Response text

        Returns:
            List of parsed proposals
        """
        proposals = []

        # Simple parsing - in production would use more sophisticated NLP
        # Look for numbered sections or clear delimiters
        lines = response_text.split("\n")

        current_proposal = {}
        proposal_count = 0

        for line in lines:
            line = line.strip()

            # Detect new proposal
            if any(
                marker in line.lower()
                for marker in ["**title", "**1.", "**2.", "**3.", "**4.", "**5."]
            ):
                # Save previous proposal
                if current_proposal.get("title"):
                    proposals.append(
                        self._create_proposal(
                            provider, proposal_count, current_proposal
                        )
                    )
                    proposal_count += 1
                current_proposal = {}

            # Extract fields
            if "title:" in line.lower():
                current_proposal["title"] = line.split(":", 1)[1].strip().strip("*")
            elif "description:" in line.lower():
                current_proposal["description"] = (
                    line.split(":", 1)[1].strip() if ":" in line else line
                )
            elif "value" in line.lower() and ":" in line:
                current_proposal["value"] = line.split(":", 1)[1].strip()
            elif "complexity:" in line.lower():
                try:
                    # Extract number
                    import re

                    match = re.search(r"(\d+)", line)
                    if match:
                        current_proposal["complexity"] = int(match.group(1))
                except ValueError:
                    pass
            elif "priority:" in line.lower():
                priority_text = line.split(":", 1)[1].strip().upper()
                if "CRITICAL" in priority_text:
                    current_proposal["priority"] = ProposalPriority.CRITICAL
                elif "HIGH" in priority_text:
                    current_proposal["priority"] = ProposalPriority.HIGH
                elif "MEDIUM" in priority_text:
                    current_proposal["priority"] = ProposalPriority.MEDIUM
                else:
                    current_proposal["priority"] = ProposalPriority.LOW
            elif "category:" in line.lower():
                current_proposal["category"] = line.split(":", 1)[1].strip()
            elif "effort:" in line.lower() or "timeline:" in line.lower():
                current_proposal["effort"] = line.split(":", 1)[1].strip()

        # Save last proposal
        if current_proposal.get("title"):
            proposals.append(
                self._create_proposal(provider, proposal_count, current_proposal)
            )

        return proposals

    def _create_proposal(
        self, provider: str, index: int, data: Dict[str, Any]
    ) -> FeatureProposal:
        """Create FeatureProposal from parsed data.

        Args:
            provider: Provider name
            index: Proposal index
            data: Parsed proposal data

        Returns:
            FeatureProposal instance
        """
        return FeatureProposal(
            id=f"{provider}-{index}",
            title=data.get("title", f"Untitled Proposal {index}"),
            description=data.get("description", "No description provided"),
            provider=provider,
            value_proposition=data.get("value", "Value not specified"),
            complexity_estimate=data.get("complexity", 5),
            priority=data.get("priority", ProposalPriority.MEDIUM),
            estimated_effort=data.get("effort"),
            category=data.get("category"),
        )

    def _parse_critiques(
        self, proposals: List[FeatureProposal], response: MultiAgentResponse
    ) -> Dict[str, ProposalCritique]:
        """Parse critiques from multi-agent response.

        Args:
            proposals: Original proposals
            response: Multi-agent response

        Returns:
            Dictionary mapping proposal_id to critique
        """
        critiques = {}

        # Initialize critiques for all proposals
        for proposal in proposals:
            critiques[proposal.id] = ProposalCritique(proposal_id=proposal.id)

        # Parse each provider's critique
        for provider, provider_response in response.responses.items():
            self._parse_provider_critique(
                provider, provider_response, proposals, critiques
            )

        # Calculate aggregate scores
        for proposal_id, critique in critiques.items():
            if critique.provider_ratings:
                avg_rating = sum(critique.provider_ratings.values()) / len(
                    critique.provider_ratings
                )
                # Normalize to 0-1
                critique.feasibility_score = min(avg_rating / 10, 1.0)
                critique.value_score = min(avg_rating / 10, 1.0)

        return critiques

    def _parse_provider_critique(
        self,
        provider: str,
        response_text: str,
        proposals: List[FeatureProposal],
        critiques: Dict[str, ProposalCritique],
    ):
        """Parse a single provider's critique.

        Args:
            provider: Provider name
            response_text: Response text
            proposals: All proposals
            critiques: Critiques dict to update
        """
        lines = response_text.split("\n")

        for line in lines:
            line = line.strip()

            # Try to match proposal IDs and ratings
            for proposal in proposals:
                if proposal.id in line or proposal.title.lower() in line.lower():
                    critique = critiques[proposal.id]

                    # Extract rating
                    import re

                    rating_match = re.search(r"rating.*?(\d+)", line, re.IGNORECASE)
                    if rating_match:
                        critique.provider_ratings[provider] = int(rating_match.group(1))

                    # Extract qualitative feedback
                    if any(
                        word in line.lower()
                        for word in ["strength", "pro", "benefit", "good"]
                    ):
                        critique.strengths.append(
                            line.split(":", 1)[1].strip() if ":" in line else line
                        )
                    elif any(
                        word in line.lower()
                        for word in ["weakness", "con", "risk", "concern"]
                    ):
                        critique.weaknesses.append(
                            line.split(":", 1)[1].strip() if ":" in line else line
                        )

    def _filter_viable_proposals(
        self,
        proposals: List[FeatureProposal],
        critiques: Dict[str, ProposalCritique],
    ) -> List[FeatureProposal]:
        """Filter proposals to keep only viable ones.

        Args:
            proposals: All proposals
            critiques: Critiques for proposals

        Returns:
            Filtered list of viable proposals
        """
        viable = []

        for proposal in proposals:
            critique = critiques.get(proposal.id)
            if not critique:
                continue

            # Keep if:
            # - Has positive ratings from providers
            # - Feasibility and value scores are reasonable
            avg_rating = (
                sum(critique.provider_ratings.values()) / len(critique.provider_ratings)
                if critique.provider_ratings
                else 5.0
            )

            if avg_rating >= 5.0 or proposal.priority in [
                ProposalPriority.CRITICAL,
                ProposalPriority.HIGH,
            ]:
                viable.append(proposal)

        # Sort by average rating
        viable.sort(
            key=lambda p: (
                sum(critiques[p.id].provider_ratings.values())
                / len(critiques[p.id].provider_ratings)
                if critiques[p.id].provider_ratings
                else 0
            ),
            reverse=True,
        )

        self.logger.debug(
            f"Filtered {len(viable)} viable proposals from {len(proposals)} total"
        )

        return viable[:20]  # Keep top 20

    def _parse_synthesized_roadmap(
        self,
        response: MultiAgentResponse,
        proposals: List[FeatureProposal],
        critiques: Dict[str, ProposalCritique],
    ) -> SynthesizedRoadmap:
        """Parse synthesized roadmap from dialectical response.

        Args:
            response: Multi-agent response
            proposals: All proposals
            critiques: All critiques

        Returns:
            Synthesized roadmap
        """
        # Combine all provider responses
        combined_response = "\n\n".join(response.responses.values())

        # Parse phases (simple extraction)
        phases = self._extract_phases(combined_response, proposals)

        # Calculate consensus confidence
        # High confidence if multiple providers agree on similar features
        consensus_confidence = self._calculate_synthesis_confidence(
            phases, proposals, critiques
        )

        # Extract provider perspectives
        provider_perspectives = {}
        for provider, provider_response in response.responses.items():
            # Extract key emphasis
            emphasis = self._extract_provider_emphasis(provider_response)
            provider_perspectives[provider] = emphasis

        # Count selected proposals
        selected_ids = set()
        for phase in phases:
            for feature in phase.get("features", []):
                selected_ids.add(feature.get("id", ""))

        return SynthesizedRoadmap(
            phases=phases,
            consensus_confidence=consensus_confidence,
            total_proposals_considered=len(proposals),
            selected_proposals=len(selected_ids),
            provider_perspectives=provider_perspectives,
            synthesis_notes=combined_response[:500],  # First 500 chars
        )

    def _extract_phases(
        self, response_text: str, proposals: List[FeatureProposal]
    ) -> List[Dict[str, Any]]:
        """Extract phases from synthesis response.

        Args:
            response_text: Combined response text
            proposals: All proposals

        Returns:
            List of phase dictionaries
        """
        phases = []

        # Simple phase extraction - look for "Phase" headers
        lines = response_text.split("\n")
        current_phase = None

        for line in lines:
            line = line.strip()

            # Detect phase header
            if "phase" in line.lower() and (":" in line or "#" in line):
                if current_phase:
                    phases.append(current_phase)

                # Parse phase info
                phase_name = line.split(":")[0].strip("#* ").strip()
                current_phase = {
                    "name": phase_name,
                    "timeline": self._extract_timeline(line),
                    "features": [],
                }

            # Extract feature references
            elif current_phase:
                # Look for proposal IDs or titles
                for proposal in proposals:
                    if proposal.id in line or proposal.title.lower() in line.lower():
                        if not any(
                            f.get("id") == proposal.id
                            for f in current_phase["features"]
                        ):
                            current_phase["features"].append(
                                {
                                    "id": proposal.id,
                                    "title": proposal.title,
                                    "description": proposal.description,
                                    "complexity": proposal.complexity_estimate,
                                    "priority": proposal.priority.value,
                                }
                            )

        # Add last phase
        if current_phase:
            phases.append(current_phase)

        # If no phases detected, create default structure
        if not phases:
            phases = [
                {
                    "name": "Phase 1: Foundation",
                    "timeline": "4-8 weeks",
                    "features": [
                        {
                            "id": p.id,
                            "title": p.title,
                            "description": p.description,
                            "complexity": p.complexity_estimate,
                            "priority": p.priority.value,
                        }
                        for p in proposals[:5]
                    ],
                }
            ]

        return phases

    def _extract_timeline(self, text: str) -> str:
        """Extract timeline from phase header.

        Args:
            text: Phase header text

        Returns:
            Timeline string
        """
        import re

        # Look for timeline patterns
        timeline_match = re.search(
            r"(\d+[-–]\d+\s+(?:weeks|months|days))", text, re.IGNORECASE
        )
        if timeline_match:
            return timeline_match.group(1)

        # Look for quarter notation
        quarter_match = re.search(r"(Q\d+\s+\d{4})", text, re.IGNORECASE)
        if quarter_match:
            return quarter_match.group(1)

        return "TBD"

    def _calculate_synthesis_confidence(
        self,
        phases: List[Dict[str, Any]],
        proposals: List[FeatureProposal],
        critiques: Dict[str, ProposalCritique],
    ) -> float:
        """Calculate consensus confidence for synthesis.

        Args:
            phases: Extracted phases
            proposals: All proposals
            critiques: All critiques

        Returns:
            Confidence score 0-1
        """
        if not phases:
            return 0.0

        # Calculate based on:
        # 1. Number of phases (3-4 is ideal)
        # 2. Features per phase (3-6 is ideal)
        # 3. Average critique scores of selected features

        phase_count_score = 1.0 if 3 <= len(phases) <= 4 else 0.7

        feature_count_scores = []
        critique_scores = []

        for phase in phases:
            features = phase.get("features", [])
            feature_count = len(features)

            # Score feature count
            if 3 <= feature_count <= 6:
                feature_count_scores.append(1.0)
            elif 2 <= feature_count <= 7:
                feature_count_scores.append(0.8)
            else:
                feature_count_scores.append(0.6)

            # Score critique quality
            for feature in features:
                feature_id = feature.get("id")
                if feature_id and feature_id in critiques:
                    critique = critiques[feature_id]
                    avg_score = (critique.feasibility_score + critique.value_score) / 2
                    critique_scores.append(avg_score)

        avg_feature_count_score = (
            sum(feature_count_scores) / len(feature_count_scores)
            if feature_count_scores
            else 0.5
        )
        avg_critique_score = (
            sum(critique_scores) / len(critique_scores) if critique_scores else 0.5
        )

        # Weighted average
        confidence = (
            0.3 * phase_count_score
            + 0.3 * avg_feature_count_score
            + 0.4 * avg_critique_score
        )

        return min(confidence, 1.0)

    def _extract_provider_emphasis(self, response_text: str) -> str:
        """Extract key emphasis from provider response.

        Args:
            response_text: Provider response

        Returns:
            Key emphasis string
        """
        # Look for emphasis keywords
        emphasis_keywords = {
            "performance": ["performance", "speed", "efficiency", "optimization"],
            "security": ["security", "authentication", "authorization", "encryption"],
            "scalability": ["scalability", "scale", "growth", "infrastructure"],
            "user experience": ["ux", "user experience", "usability", "interface"],
            "innovation": ["innovative", "novel", "creative", "new"],
            "best practices": ["best practice", "standard", "industry", "compliance"],
        }

        response_lower = response_text.lower()
        keyword_counts = {}

        for emphasis, keywords in emphasis_keywords.items():
            count = sum(response_lower.count(keyword) for keyword in keywords)
            if count > 0:
                keyword_counts[emphasis] = count

        if keyword_counts:
            # Return top emphasis
            top_emphasis = max(keyword_counts.items(), key=lambda x: x[1])
            return top_emphasis[0].title()

        return "General development"
