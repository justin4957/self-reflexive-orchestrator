"""Roadmap generator that creates structured development roadmaps.

Combines codebase analysis, multi-agent ideation, and formatting
to produce actionable, GitHub-ready roadmaps.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..analyzers.codebase_analyzer import CodebaseAnalyzer, CodebaseAnalysis
from ..analyzers.multi_agent_analyzer import (
    MultiAgentAnalyzer,
    MultiAgentAnalysisResult,
)
from ..cycles.multi_agent_ideation import (
    MultiAgentIdeation,
    IdeationResult,
    SynthesizedRoadmap,
)
from ..integrations.multi_agent_coder_client import MultiAgentCoderClient
from ..core.logger import AuditLogger


@dataclass
class RoadmapMetadata:
    """Metadata for generated roadmap."""

    generated_at: datetime
    roadmap_id: str
    repository_path: str
    total_cost: float
    total_tokens: int
    analysis_duration_seconds: float
    ideation_duration_seconds: float
    consensus_confidence: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "generated_at": self.generated_at.isoformat(),
            "roadmap_id": self.roadmap_id,
            "repository_path": self.repository_path,
            "total_cost": self.total_cost,
            "total_tokens": self.total_tokens,
            "analysis_duration_seconds": self.analysis_duration_seconds,
            "ideation_duration_seconds": self.ideation_duration_seconds,
            "consensus_confidence": self.consensus_confidence,
        }


@dataclass
class GeneratedRoadmap:
    """Complete generated roadmap with all components."""

    metadata: RoadmapMetadata
    codebase_analysis: CodebaseAnalysis
    multi_agent_analysis: MultiAgentAnalysisResult
    ideation_result: IdeationResult
    markdown_content: str
    file_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "metadata": self.metadata.to_dict(),
            "codebase_analysis": self.codebase_analysis.to_dict(),
            "multi_agent_analysis": self.multi_agent_analysis.to_dict(),
            "ideation_result": self.ideation_result.to_dict(),
            "markdown_content": self.markdown_content,
            "file_path": self.file_path,
        }


class RoadmapGenerator:
    """Generates structured development roadmaps using multi-agent collaboration.

    Responsibilities:
    - Orchestrate complete roadmap generation pipeline
    - Combine codebase analysis with multi-agent ideation
    - Format roadmap as structured markdown document
    - Include timelines, dependencies, and success metrics
    - Generate GitHub-ready documentation
    - Store roadmap for future reference
    """

    def __init__(
        self,
        repository_path: str,
        multi_agent_client: MultiAgentCoderClient,
        logger: AuditLogger,
        output_dir: Optional[str] = None,
    ):
        """Initialize roadmap generator.

        Args:
            repository_path: Path to repository to analyze
            multi_agent_client: Multi-agent-coder client
            logger: Audit logger
            output_dir: Optional directory for roadmap output
        """
        self.repository_path = Path(repository_path)
        self.multi_agent_client = multi_agent_client
        self.logger = logger
        self.output_dir = (
            Path(output_dir) if output_dir else self.repository_path / "roadmaps"
        )

        # Initialize components
        self.codebase_analyzer = CodebaseAnalyzer(str(self.repository_path), logger)
        self.multi_agent_analyzer = MultiAgentAnalyzer(multi_agent_client, logger)
        self.ideation_engine = MultiAgentIdeation(multi_agent_client, logger)

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_roadmap(
        self,
        roadmap_id: Optional[str] = None,
        project_goals: Optional[List[str]] = None,
        save_to_file: bool = True,
    ) -> GeneratedRoadmap:
        """Generate complete development roadmap.

        Args:
            roadmap_id: Optional ID for roadmap (auto-generated if None)
            project_goals: Optional list of specific project goals
            save_to_file: Whether to save roadmap to file

        Returns:
            GeneratedRoadmap with all components
        """
        start_time = datetime.now(timezone.utc)

        # Generate roadmap ID if not provided
        if not roadmap_id:
            roadmap_id = f"roadmap-{start_time.strftime('%Y%m%d-%H%M%S')}"

        self.logger.info(
            "Starting roadmap generation",
            roadmap_id=roadmap_id,
            repository=str(self.repository_path),
            project_goals=project_goals,
        )

        # Phase 1: Analyze codebase
        self.logger.info("Phase 1: Analyzing codebase structure and metrics")
        analysis_start = datetime.now(timezone.utc)
        codebase_analysis = self.codebase_analyzer.analyze()
        analysis_duration = (
            datetime.now(timezone.utc) - analysis_start
        ).total_seconds()

        # Phase 2: Multi-agent analysis
        self.logger.info("Phase 2: Multi-agent codebase analysis")
        multi_agent_analysis = self.multi_agent_analyzer.analyze_with_multi_agent(
            codebase_analysis, f"{roadmap_id}-analysis"
        )

        # Phase 3: Multi-agent ideation
        self.logger.info("Phase 3: Multi-agent ideation and synthesis")
        ideation_start = datetime.now(timezone.utc)
        ideation_result = self.ideation_engine.generate_roadmap(
            codebase_analysis, multi_agent_analysis, project_goals
        )
        ideation_duration = (
            datetime.now(timezone.utc) - ideation_start
        ).total_seconds()

        # Phase 4: Format as markdown
        self.logger.info("Phase 4: Formatting roadmap as markdown")
        markdown_content = self._format_roadmap_markdown(
            roadmap_id,
            codebase_analysis,
            multi_agent_analysis,
            ideation_result,
            project_goals,
        )

        # Create metadata
        metadata = RoadmapMetadata(
            generated_at=start_time,
            roadmap_id=roadmap_id,
            repository_path=str(self.repository_path),
            total_cost=ideation_result.total_cost,
            total_tokens=ideation_result.total_tokens,
            analysis_duration_seconds=analysis_duration,
            ideation_duration_seconds=ideation_duration,
            consensus_confidence=ideation_result.synthesized_roadmap.consensus_confidence,
        )

        # Save to file if requested
        file_path = None
        if save_to_file:
            file_path = self._save_roadmap(roadmap_id, markdown_content)
            self.logger.info(f"Roadmap saved to: {file_path}")

        roadmap = GeneratedRoadmap(
            metadata=metadata,
            codebase_analysis=codebase_analysis,
            multi_agent_analysis=multi_agent_analysis,
            ideation_result=ideation_result,
            markdown_content=markdown_content,
            file_path=str(file_path) if file_path else None,
        )

        total_duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        self.logger.info(
            "Roadmap generation complete",
            roadmap_id=roadmap_id,
            total_duration_seconds=total_duration,
            total_cost=metadata.total_cost,
            consensus_confidence=metadata.consensus_confidence,
            phases=len(ideation_result.synthesized_roadmap.phases),
            selected_features=ideation_result.synthesized_roadmap.selected_proposals,
        )

        return roadmap

    def _format_roadmap_markdown(
        self,
        roadmap_id: str,
        codebase_analysis: CodebaseAnalysis,
        multi_agent_analysis: MultiAgentAnalysisResult,
        ideation_result: IdeationResult,
        project_goals: Optional[List[str]],
    ) -> str:
        """Format roadmap as GitHub-ready markdown.

        Args:
            roadmap_id: Roadmap identifier
            codebase_analysis: Codebase analysis
            multi_agent_analysis: Multi-agent analysis
            ideation_result: Ideation result
            project_goals: Optional project goals

        Returns:
            Formatted markdown string
        """
        synthesized = ideation_result.synthesized_roadmap
        consensus = multi_agent_analysis.consensus

        lines = [
            f"# Development Roadmap - {roadmap_id}",
            "",
            f"**Generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"**Repository**: {codebase_analysis.repository_path}",
            f"**Consensus Confidence**: {synthesized.consensus_confidence:.1%}",
            "",
            "---",
            "",
        ]

        # Executive Summary
        lines.extend(
            self._format_executive_summary(
                codebase_analysis, multi_agent_analysis, ideation_result
            )
        )

        # Project Goals
        if project_goals:
            lines.extend(["", "## Project Goals", ""])
            for goal in project_goals:
                lines.append(f"- {goal}")
            lines.append("")

        # Current State
        lines.extend(self._format_current_state(codebase_analysis, consensus))

        # Roadmap Phases
        lines.extend(self._format_phases(synthesized.phases, ideation_result.critiques))

        # Multi-Agent Insights
        lines.extend(
            self._format_multi_agent_insights(synthesized, multi_agent_analysis)
        )

        # Implementation Notes
        lines.extend(self._format_implementation_notes(synthesized))

        # Appendix: All Proposals
        lines.extend(self._format_all_proposals(ideation_result))

        # Footer
        lines.extend(
            [
                "",
                "---",
                "",
                f"**Roadmap ID**: `{roadmap_id}`",
                f"**Total Cost**: ${ideation_result.total_cost:.4f}",
                f"**Total Proposals Considered**: {synthesized.total_proposals_considered}",
                f"**Selected Features**: {synthesized.selected_proposals}",
                f"**Generation Time**: {ideation_result.duration_seconds:.1f}s",
                "",
                "🤖 *Generated by Self-Reflexive Orchestrator using Multi-Agent Collaboration*",
            ]
        )

        return "\n".join(lines)

    def _format_executive_summary(
        self,
        codebase_analysis: CodebaseAnalysis,
        multi_agent_analysis: MultiAgentAnalysisResult,
        ideation_result: IdeationResult,
    ) -> List[str]:
        """Format executive summary section.

        Args:
            codebase_analysis: Codebase analysis
            multi_agent_analysis: Multi-agent analysis
            ideation_result: Ideation result

        Returns:
            List of markdown lines
        """
        metrics = codebase_analysis.metrics
        consensus = multi_agent_analysis.consensus
        synthesized = ideation_result.synthesized_roadmap

        lines = [
            "## Executive Summary",
            "",
            f"This roadmap outlines **{synthesized.selected_proposals} priority features** across **{len(synthesized.phases)} development phases** ",
            f"for the codebase at `{codebase_analysis.repository_path}`.",
            "",
            "**Key Highlights:**",
            f"- **{metrics.total_files}** files analyzed ({metrics.total_code_lines:,} lines of code)",
            f"- **{len(multi_agent_analysis.provider_insights)}** AI perspectives consulted",
            f"- **{synthesized.consensus_confidence:.0%}** consensus confidence",
            f"- **{len([p for p in consensus.top_priorities if p['priority'] == 'high'])}** high-priority improvements identified",
            "",
        ]

        return lines

    def _format_current_state(
        self,
        codebase_analysis: CodebaseAnalysis,
        consensus: Any,
    ) -> List[str]:
        """Format current state section.

        Args:
            codebase_analysis: Codebase analysis
            consensus: Consensus insights

        Returns:
            List of markdown lines
        """
        metrics = codebase_analysis.metrics
        patterns = codebase_analysis.patterns

        lines = [
            "## Current State Assessment",
            "",
            "### Codebase Metrics",
            "",
            f"- **Total Files**: {metrics.total_files}",
            f"- **Lines of Code**: {metrics.total_code_lines:,}",
            f"- **Languages**: {', '.join(metrics.languages.keys())}",
            f"- **Average Complexity**: {metrics.avg_complexity:.1f}",
            f"- **Test Files**: {patterns.get('test_files_count', 0)}",
            f"- **Documentation Files**: {len(patterns.get('documentation_files', []))}",
            "",
            "### Quality Assessment (Multi-Agent Analysis)",
            "",
            f"- **Architecture Rating**: {consensus.overall_architecture_rating:.1f}/10",
            f"- **Code Quality Rating**: {consensus.overall_quality_rating:.1f}/10",
            f"- **Consensus Confidence**: {consensus.consensus_confidence:.1%}",
            "",
        ]

        # Add consensus patterns
        if consensus.consensus_patterns:
            lines.extend(
                [
                    "**Identified Patterns:**",
                    "",
                ]
            )
            for pattern in consensus.consensus_patterns:
                lines.append(f"- {pattern}")
            lines.append("")

        # Add top priorities
        if consensus.top_priorities:
            lines.extend(
                [
                    "**Top Priorities (from Multi-Agent Analysis):**",
                    "",
                ]
            )
            for i, priority in enumerate(consensus.top_priorities[:5], 1):
                lines.append(
                    f"{i}. **[{priority['priority'].upper()}]** {priority['description']} "
                    f"(confidence: {priority['confidence']:.0%})"
                )
            lines.append("")

        return lines

    def _format_phases(
        self, phases: List[Dict[str, Any]], critiques: Dict[str, Any]
    ) -> List[str]:
        """Format roadmap phases section.

        Args:
            phases: List of phase dictionaries
            critiques: Critiques for proposals

        Returns:
            List of markdown lines
        """
        lines = [
            "## Roadmap Phases",
            "",
        ]

        for phase_num, phase in enumerate(phases, 1):
            phase_name = phase.get("name", f"Phase {phase_num}")
            timeline = phase.get("timeline", "TBD")
            features = phase.get("features", [])

            lines.extend(
                [
                    f"### {phase_name}",
                    "",
                    f"**Timeline**: {timeline}",
                    f"**Features**: {len(features)}",
                    "",
                ]
            )

            # List features
            for feature_num, feature in enumerate(features, 1):
                feature_id = feature.get("id", "")
                title = feature.get("title", "Untitled")
                description = feature.get("description", "")
                complexity = feature.get("complexity", 5)
                priority = feature.get("priority", "medium")

                lines.extend(
                    [
                        f"#### {phase_num}.{feature_num} {title}",
                        "",
                        f"**Priority**: {priority.upper()}  ",
                        f"**Complexity**: {complexity}/10",
                        "",
                        f"{description}",
                        "",
                    ]
                )

                # Add critique info if available
                if feature_id and feature_id in critiques:
                    critique = critiques[feature_id]
                    if critique.strengths:
                        lines.append(
                            f"**Strengths**: {', '.join(critique.strengths[:2])}"
                        )
                    if critique.weaknesses:
                        lines.append(
                            f"**Concerns**: {', '.join(critique.weaknesses[:2])}"
                        )
                    lines.append("")

        return lines

    def _format_multi_agent_insights(
        self,
        synthesized: SynthesizedRoadmap,
        multi_agent_analysis: MultiAgentAnalysisResult,
    ) -> List[str]:
        """Format multi-agent insights section.

        Args:
            synthesized: Synthesized roadmap
            multi_agent_analysis: Multi-agent analysis

        Returns:
            List of markdown lines
        """
        lines = [
            "## Multi-Agent Insights",
            "",
            "This roadmap was generated using insights from multiple AI perspectives:",
            "",
        ]

        # Provider perspectives
        for provider, emphasis in synthesized.provider_perspectives.items():
            provider_insight = multi_agent_analysis.provider_insights.get(provider)
            lines.append(f"### {provider.upper()}")
            lines.append("")
            lines.append(f"**Focus**: {emphasis}")

            if provider_insight:
                if provider_insight.architecture_rating:
                    lines.append(
                        f"**Architecture Rating**: {provider_insight.architecture_rating}/10"
                    )
                if provider_insight.recommendations:
                    lines.append("")
                    lines.append("**Key Recommendations:**")
                    for rec in provider_insight.recommendations[:3]:
                        lines.append(f"- {rec}")

            lines.append("")

        # Synthesis notes
        if synthesized.synthesis_notes:
            lines.extend(
                [
                    "### Synthesis Approach",
                    "",
                    "The roadmap was synthesized through dialectical collaboration:",
                    "",
                    f"> {synthesized.synthesis_notes[:300]}...",
                    "",
                ]
            )

        return lines

    def _format_implementation_notes(
        self, synthesized: SynthesizedRoadmap
    ) -> List[str]:
        """Format implementation notes section.

        Args:
            synthesized: Synthesized roadmap

        Returns:
            List of markdown lines
        """
        lines = [
            "## Implementation Notes",
            "",
            "### Dependencies",
            "",
            "- Features should be implemented in phase order",
            "- Each phase builds on the previous phase",
            "- Dependencies within phases should be resolved first",
            "",
            "### Success Metrics",
            "",
            "Track progress with these metrics:",
            "",
            "- **Completion Rate**: Features completed vs planned",
            "- **Quality Metrics**: Test coverage, code review scores",
            "- **Timeline Adherence**: Actual vs estimated timelines",
            "- **Value Delivery**: User satisfaction, performance improvements",
            "",
            "### Review Cadence",
            "",
            "- **Weekly**: Review progress within current phase",
            "- **Monthly**: Adjust priorities based on learnings",
            "- **Quarterly**: Generate updated roadmap with new insights",
            "",
        ]

        return lines

    def _format_all_proposals(self, ideation_result: IdeationResult) -> List[str]:
        """Format appendix with all proposals.

        Args:
            ideation_result: Ideation result

        Returns:
            List of markdown lines
        """
        lines = [
            "## Appendix: All Proposals Considered",
            "",
            f"Total proposals generated: **{len(ideation_result.proposals)}**",
            "",
            "<details>",
            "<summary>Click to expand all proposals</summary>",
            "",
        ]

        # Group by provider
        by_provider = {}
        for proposal in ideation_result.proposals:
            if proposal.provider not in by_provider:
                by_provider[proposal.provider] = []
            by_provider[proposal.provider].append(proposal)

        for provider, proposals in by_provider.items():
            lines.extend(
                [
                    f"### {provider.upper()} Proposals ({len(proposals)})",
                    "",
                ]
            )

            for proposal in proposals:
                lines.extend(
                    [
                        f"**{proposal.title}** (ID: `{proposal.id}`)",
                        f"- Complexity: {proposal.complexity_estimate}/10",
                        f"- Priority: {proposal.priority.value}",
                        f"- Value: {proposal.value_proposition}",
                        "",
                    ]
                )

        lines.extend(
            [
                "</details>",
                "",
            ]
        )

        return lines

    def _save_roadmap(self, roadmap_id: str, markdown_content: str) -> Path:
        """Save roadmap to file.

        Args:
            roadmap_id: Roadmap identifier
            markdown_content: Markdown content

        Returns:
            Path to saved file
        """
        filename = f"{roadmap_id}.md"
        file_path = self.output_dir / filename

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        self.logger.info(
            "Roadmap saved",
            roadmap_id=roadmap_id,
            file_path=str(file_path),
        )

        return file_path
