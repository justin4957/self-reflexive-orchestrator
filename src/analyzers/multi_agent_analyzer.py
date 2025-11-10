"""Multi-agent analyzer for comprehensive codebase insights.

Uses multiple AI providers to analyze codebase from diverse perspectives
and build consensus on improvement opportunities.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..integrations.multi_agent_coder_client import (
    MultiAgentCoderClient,
    MultiAgentStrategy,
    MultiAgentResponse,
)
from ..core.logger import AuditLogger
from .codebase_analyzer import CodebaseAnalysis


@dataclass
class ProviderInsight:
    """Insight from a single AI provider."""

    provider: str
    architecture_rating: Optional[int] = None  # 1-10
    architecture_patterns: List[str] = field(default_factory=list)
    code_quality_rating: Optional[int] = None  # 1-10
    technical_debt_areas: List[str] = field(default_factory=list)
    improvement_opportunities: List[str] = field(default_factory=list)
    security_concerns: List[str] = field(default_factory=list)
    performance_issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "provider": self.provider,
            "architecture_rating": self.architecture_rating,
            "architecture_patterns": self.architecture_patterns,
            "code_quality_rating": self.code_quality_rating,
            "technical_debt_areas": self.technical_debt_areas,
            "improvement_opportunities": self.improvement_opportunities,
            "security_concerns": self.security_concerns,
            "performance_issues": self.performance_issues,
            "recommendations": self.recommendations,
        }


@dataclass
class ConsensusInsights:
    """Consensus insights from multiple providers."""

    overall_architecture_rating: float
    overall_quality_rating: float
    consensus_patterns: List[str]
    top_priorities: List[
        Dict[str, Any]
    ]  # [{priority, category, description, confidence}]
    consensus_confidence: float  # 0-1, how much AIs agree
    divergent_opinions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "overall_architecture_rating": self.overall_architecture_rating,
            "overall_quality_rating": self.overall_quality_rating,
            "consensus_patterns": self.consensus_patterns,
            "top_priorities": self.top_priorities,
            "consensus_confidence": self.consensus_confidence,
            "divergent_opinions": self.divergent_opinions,
        }


@dataclass
class MultiAgentAnalysisResult:
    """Result of multi-agent codebase analysis."""

    analysis_id: str
    analyzed_at: datetime
    provider_insights: Dict[str, ProviderInsight]  # provider -> insight
    consensus: ConsensusInsights
    raw_codebase_analysis: CodebaseAnalysis

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "analysis_id": self.analysis_id,
            "analyzed_at": self.analyzed_at.isoformat(),
            "provider_insights": {
                k: v.to_dict() for k, v in self.provider_insights.items()
            },
            "consensus": self.consensus.to_dict(),
            "raw_codebase_analysis": self.raw_codebase_analysis.to_dict(),
        }


class MultiAgentAnalyzer:
    """Analyzes codebase using multiple AI perspectives.

    Responsibilities:
    - Coordinate multi-agent codebase analysis
    - Each AI analyzes from unique perspective
    - Build consensus on findings
    - Prioritize improvement opportunities
    - Identify gaps and technical debt
    """

    PROVIDER_FOCUS = {
        "anthropic": "Enterprise features, architecture patterns, and security",
        "deepseek": "Performance optimization, code quality, and technical debt",
        "openai": "Innovation opportunities, user experience, and design patterns",
        "perplexity": "Industry best practices, standards compliance, and research",
    }

    def __init__(
        self,
        multi_agent_client: MultiAgentCoderClient,
        logger: AuditLogger,
    ):
        """Initialize multi-agent analyzer.

        Args:
            multi_agent_client: Multi-agent-coder client
            logger: Audit logger
        """
        self.multi_agent_client = multi_agent_client
        self.logger = logger

    def analyze_with_multi_agent(
        self, codebase_analysis: CodebaseAnalysis, analysis_id: str
    ) -> MultiAgentAnalysisResult:
        """Analyze codebase with multiple AI perspectives.

        Args:
            codebase_analysis: Raw codebase analysis data
            analysis_id: Unique ID for this analysis

        Returns:
            MultiAgentAnalysisResult with insights from all providers
        """
        self.logger.info(
            "Starting multi-agent codebase analysis",
            analysis_id=analysis_id,
        )

        # Get architecture analysis from all providers
        architecture_insights = self._analyze_architecture(codebase_analysis)

        # Get technical debt assessment
        debt_insights = self._analyze_technical_debt(codebase_analysis)

        # Identify gaps and missing features
        gap_insights = self._identify_gaps(codebase_analysis)

        # Build provider-specific insights
        provider_insights = self._build_provider_insights(
            architecture_insights, debt_insights, gap_insights
        )

        # Build consensus
        consensus = self._build_consensus(provider_insights)

        result = MultiAgentAnalysisResult(
            analysis_id=analysis_id,
            analyzed_at=datetime.now(timezone.utc),
            provider_insights=provider_insights,
            consensus=consensus,
            raw_codebase_analysis=codebase_analysis,
        )

        self.logger.info(
            "Multi-agent analysis complete",
            analysis_id=analysis_id,
            consensus_confidence=consensus.consensus_confidence,
            top_priorities_count=len(consensus.top_priorities),
        )

        return result

    def _analyze_architecture(self, analysis: CodebaseAnalysis) -> MultiAgentResponse:
        """Analyze architecture from multiple perspectives.

        Args:
            analysis: Codebase analysis

        Returns:
            MultiAgentResponse with architecture insights
        """
        prompt = f"""Analyze this codebase architecture:

**Structure:**
- Total Files: {analysis.metrics.total_files}
- Languages: {', '.join(analysis.metrics.languages.keys())}
- Lines of Code: {analysis.metrics.total_code_lines:,}

**Patterns Detected:**
{self._format_patterns(analysis.patterns)}

**Dependencies:**
- Package Managers: {', '.join(analysis.dependencies.package_managers)}
- Total Dependencies: {sum(len(deps) for deps in analysis.dependencies.dependencies.values())}

From your perspective ({self.PROVIDER_FOCUS.get('your_provider', 'general')}), evaluate:

1. **Architecture Quality** (rate 1-10): How well is the code organized?
2. **Patterns Used**: What architectural patterns do you see?
3. **Scalability**: Can this architecture scale?
4. **Maintainability**: How easy is it to maintain?
5. **Recommendations**: Top 3 architectural improvements

Provide specific, actionable insights.
"""

        response = self.multi_agent_client.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.ALL,
            timeout=120,
        )

        return response

    def _analyze_technical_debt(self, analysis: CodebaseAnalysis) -> MultiAgentResponse:
        """Analyze technical debt from multiple perspectives.

        Args:
            analysis: Codebase analysis

        Returns:
            MultiAgentResponse with debt assessment
        """
        prompt = f"""Assess technical debt in this codebase:

**Code Metrics:**
- Average Complexity: {analysis.metrics.avg_complexity:.1f}
- Test Coverage: {analysis.metrics.test_coverage or 'Unknown'}
- Code/Comment Ratio: {analysis.metrics.total_code_lines / max(analysis.metrics.total_comment_lines, 1):.1f}

**Testing:**
- Has Tests: {analysis.patterns.get('has_tests', False)}
- Test Files: {analysis.patterns.get('test_files_count', 0)}

**Documentation:**
- Has Docs: {analysis.patterns.get('has_documentation', False)}

From your perspective ({self.PROVIDER_FOCUS.get('your_provider', 'general')}), identify:

1. **High-Priority Technical Debt**: What needs urgent attention?
2. **Code Quality Issues**: What code smells do you see?
3. **Missing Tests**: Where is test coverage inadequate?
4. **Performance Bottlenecks**: What might be slow?
5. **Security Concerns**: Any security issues?

Prioritize by impact and effort to fix.
"""

        response = self.multi_agent_client.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.DIALECTICAL,
            timeout=120,
        )

        return response

    def _identify_gaps(self, analysis: CodebaseAnalysis) -> MultiAgentResponse:
        """Identify gaps and missing features.

        Args:
            analysis: Codebase analysis

        Returns:
            MultiAgentResponse with gap analysis
        """
        prompt = f"""Identify gaps and missing features in this codebase:

**Current State:**
- Languages: {', '.join(analysis.metrics.languages.keys())}
- Frameworks: {', '.join(analysis.patterns.get('frameworks', {}).keys())}
- Has Tests: {analysis.patterns.get('has_tests', False)}
- Has Documentation: {analysis.patterns.get('has_documentation', False)}

**Architecture:**
- Pattern: {analysis.patterns.get('architecture_pattern', 'Unknown')}

From your perspective ({self.PROVIDER_FOCUS.get('your_provider', 'general')}), identify:

1. **Missing Features**: What essential features are absent?
2. **Incomplete Implementations**: What's half-done?
3. **Missing Error Handling**: Where are error handling gaps?
4. **Missing Documentation**: What needs documentation?
5. **Missing Tests**: What critical paths lack tests?

Focus on highest-value additions.
"""

        response = self.multi_agent_client.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.ALL,
            timeout=120,
        )

        return response

    def _build_provider_insights(
        self,
        architecture: MultiAgentResponse,
        debt: MultiAgentResponse,
        gaps: MultiAgentResponse,
    ) -> Dict[str, ProviderInsight]:
        """Build insights for each provider.

        Args:
            architecture: Architecture analysis responses
            debt: Technical debt responses
            gaps: Gap analysis responses

        Returns:
            Dictionary mapping provider to insights
        """
        provider_insights = {}

        # Combine responses from all analyses
        all_providers = set(architecture.responses.keys())

        for provider in all_providers:
            arch_response = architecture.responses.get(provider, "")
            debt_response = debt.responses.get(provider, "")
            gap_response = gaps.responses.get(provider, "")

            insight = self._parse_provider_response(
                provider, arch_response, debt_response, gap_response
            )
            provider_insights[provider] = insight

        return provider_insights

    def _parse_provider_response(
        self,
        provider: str,
        arch_response: str,
        debt_response: str,
        gap_response: str,
    ) -> ProviderInsight:
        """Parse responses from a provider into structured insight.

        Args:
            provider: Provider name
            arch_response: Architecture analysis response
            debt_response: Technical debt response
            gap_response: Gap analysis response

        Returns:
            ProviderInsight with extracted data
        """
        # Simple parsing - extract ratings and key points
        # In production, this would use more sophisticated parsing

        insight = ProviderInsight(provider=provider)

        # Extract architecture rating (look for numbers 1-10)
        import re

        rating_match = re.search(
            r"(?:rate|rating|score).*?(\d{1,2})/10", arch_response, re.IGNORECASE
        )
        if rating_match:
            rating = int(rating_match.group(1))
            if 1 <= rating <= 10:
                insight.architecture_rating = rating

        # Extract patterns mentioned
        patterns = [
            "MVC",
            "Singleton",
            "Factory",
            "Repository",
            "Microservices",
            "Monolithic",
        ]
        for pattern in patterns:
            if pattern.lower() in arch_response.lower():
                insight.architecture_patterns.append(pattern)

        # Extract recommendations (look for numbered lists or bullet points)
        recommendations = re.findall(
            r"(?:recommend|suggest).*?[:\-]\s*(.+?)(?:\n|$)",
            arch_response,
            re.IGNORECASE,
        )
        insight.recommendations.extend(recommendations[:3])

        # Extract technical debt areas from debt response
        debt_keywords = ["refactor", "duplicate", "complex", "outdated", "legacy"]
        for keyword in debt_keywords:
            if keyword in debt_response.lower():
                insight.technical_debt_areas.append(keyword.capitalize())

        # Extract improvement opportunities from gap response
        gap_keywords = ["missing", "need", "should add", "implement", "enhance"]
        lines = gap_response.split("\n")
        for line in lines:
            if any(keyword in line.lower() for keyword in gap_keywords):
                clean_line = line.strip().lstrip("-*•").strip()
                if clean_line and len(clean_line) < 200:
                    insight.improvement_opportunities.append(clean_line)

        return insight

    def _build_consensus(
        self, provider_insights: Dict[str, ProviderInsight]
    ) -> ConsensusInsights:
        """Build consensus from provider insights.

        Args:
            provider_insights: Insights from each provider

        Returns:
            ConsensusInsights with aggregated data
        """
        if not provider_insights:
            return ConsensusInsights(
                overall_architecture_rating=0.0,
                overall_quality_rating=0.0,
                consensus_patterns=[],
                top_priorities=[],
                consensus_confidence=0.0,
            )

        # Calculate average ratings
        arch_ratings = [
            p.architecture_rating
            for p in provider_insights.values()
            if p.architecture_rating is not None
        ]
        avg_arch_rating = sum(arch_ratings) / len(arch_ratings) if arch_ratings else 0.0

        quality_ratings = [
            p.code_quality_rating
            for p in provider_insights.values()
            if p.code_quality_rating is not None
        ]
        avg_quality_rating = (
            sum(quality_ratings) / len(quality_ratings) if quality_ratings else 0.0
        )

        # Find consensus patterns (mentioned by multiple providers)
        pattern_counts = {}
        for insight in provider_insights.values():
            for pattern in insight.architecture_patterns:
                pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

        consensus_patterns = [
            pattern
            for pattern, count in pattern_counts.items()
            if count >= len(provider_insights) / 2
        ]

        # Aggregate priorities from all providers
        all_priorities = []
        for provider, insight in provider_insights.items():
            for opp in insight.improvement_opportunities[:5]:
                all_priorities.append(
                    {
                        "provider": provider,
                        "description": opp,
                        "category": "improvement",
                    }
                )
            for debt in insight.technical_debt_areas[:3]:
                all_priorities.append(
                    {"provider": provider, "description": debt, "category": "debt"}
                )

        # Build consensus priorities (mentioned by multiple providers)
        priority_counts = {}
        for priority in all_priorities:
            desc = priority["description"].lower()
            priority_counts[desc] = priority_counts.get(desc, []) + [priority]

        top_priorities = []
        for desc, priorities in sorted(
            priority_counts.items(), key=lambda x: len(x[1]), reverse=True
        )[:10]:
            confidence = len(priorities) / len(provider_insights)
            if confidence >= 0.5:  # At least half of providers mentioned it
                top_priorities.append(
                    {
                        "priority": "high" if confidence > 0.7 else "medium",
                        "category": priorities[0]["category"],
                        "description": priorities[0]["description"],
                        "confidence": confidence,
                        "mentioned_by": [p["provider"] for p in priorities],
                    }
                )

        # Calculate consensus confidence (how much providers agree)
        # Based on rating variance and priority overlap
        rating_variance = (
            sum((r - avg_arch_rating) ** 2 for r in arch_ratings) / len(arch_ratings)
            if arch_ratings
            else 0
        )
        rating_agreement = max(0, 1 - (rating_variance / 25))  # Normalize to 0-1

        priority_overlap = len(top_priorities) / max(len(all_priorities), 1)

        consensus_confidence = (rating_agreement + priority_overlap) / 2

        return ConsensusInsights(
            overall_architecture_rating=avg_arch_rating,
            overall_quality_rating=avg_quality_rating,
            consensus_patterns=consensus_patterns,
            top_priorities=top_priorities,
            consensus_confidence=consensus_confidence,
        )

    def _format_patterns(self, patterns: Dict[str, Any]) -> str:
        """Format patterns dict for display.

        Args:
            patterns: Patterns dictionary

        Returns:
            Formatted string
        """
        lines = []
        if patterns.get("has_tests"):
            lines.append(f"- Tests: {patterns.get('test_files_count', 0)} test files")
        if patterns.get("has_documentation"):
            lines.append(
                f"- Documentation: {len(patterns.get('documentation_files', []))} docs"
            )
        if patterns.get("frameworks"):
            frameworks = ", ".join(patterns["frameworks"].keys())
            lines.append(f"- Frameworks: {frameworks}")
        if patterns.get("architecture_pattern"):
            lines.append(f"- Architecture: {patterns['architecture_pattern']}")

        return "\n".join(lines) if lines else "- No patterns detected"
