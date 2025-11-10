"""Multi-agent risk assessment using multiple AI perspectives.

Uses multi-agent-coder to get comprehensive risk analysis from multiple
AI providers, building consensus on operation safety.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..integrations.multi_agent_coder_client import (
    MultiAgentCoderClient,
    MultiAgentStrategy,
    MultiAgentResponse,
)
from ..core.logger import AuditLogger
from .guards import Operation, RiskLevel, GuardDecision


@dataclass
class RiskAssessment:
    """Risk assessment from multi-agent analysis."""

    operation: Operation
    risk_level: RiskLevel
    consensus_strength: float  # 0.0-1.0
    provider_votes: Dict[str, str]  # provider -> risk level
    rationale: str
    potential_impacts: List[str] = field(default_factory=list)
    hidden_dependencies: List[str] = field(default_factory=list)
    rollback_complexity: str = ""  # Description of rollback difficulty
    blast_radius: str = ""  # Description of impact scope
    unanimous: bool = False
    assessed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "operation": self.operation.to_dict(),
            "risk_level": self.risk_level.value,
            "consensus_strength": self.consensus_strength,
            "provider_votes": self.provider_votes,
            "rationale": self.rationale,
            "potential_impacts": self.potential_impacts,
            "hidden_dependencies": self.hidden_dependencies,
            "rollback_complexity": self.rollback_complexity,
            "blast_radius": self.blast_radius,
            "unanimous": self.unanimous,
            "assessed_at": self.assessed_at.isoformat(),
        }


class MultiAgentRiskAssessor:
    """Assesses operation risk using multiple AI perspectives.

    Responsibilities:
    - Query multiple AI providers for risk analysis
    - Build consensus on risk level
    - Extract potential impacts and dependencies
    - Assess rollback complexity
    - Provide comprehensive rationale
    """

    # Risk hierarchy for consensus
    RISK_HIERARCHY = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

    # Consensus thresholds for each risk level
    CONSENSUS_THRESHOLDS = {
        RiskLevel.CRITICAL: 0.25,  # Any provider says critical -> critical
        RiskLevel.HIGH: 0.50,  # 50%+ say high -> high
        RiskLevel.MEDIUM: 0.66,  # 66%+ say medium -> medium
        RiskLevel.LOW: 0.75,  # 75%+ say low -> low
    }

    def __init__(
        self,
        multi_agent_client: MultiAgentCoderClient,
        logger: AuditLogger,
    ):
        """Initialize risk assessor.

        Args:
            multi_agent_client: Multi-agent-coder client
            logger: Audit logger
        """
        self.multi_agent_client = multi_agent_client
        self.logger = logger

        self.logger.info("multi_agent_risk_assessor_initialized")

    def assess_operation(
        self,
        operation: Operation,
        additional_context: Optional[str] = None,
    ) -> RiskAssessment:
        """Assess risk of an operation using multiple AI perspectives.

        Args:
            operation: Operation to assess
            additional_context: Optional additional context

        Returns:
            RiskAssessment with consensus and rationale
        """
        self.logger.info(
            "assessing_operation_risk",
            operation_type=operation.operation_type.value,
            files_count=len(operation.files),
        )

        # Build comprehensive prompt
        prompt = self._build_assessment_prompt(operation, additional_context)

        # Query all providers
        response = self.multi_agent_client.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.ALL,
            timeout=180,  # 3 minutes for thorough analysis
        )

        if not response.success:
            self.logger.error(
                "risk_assessment_failed",
                operation_type=operation.operation_type.value,
                error=response.error,
            )
            # Default to CRITICAL on failure (safety-first)
            return RiskAssessment(
                operation=operation,
                risk_level=RiskLevel.CRITICAL,
                consensus_strength=1.0,
                provider_votes={},
                rationale=f"Risk assessment failed: {response.error}. Defaulting to CRITICAL for safety.",
                unanimous=True,
            )

        # Parse and synthesize risk assessment
        assessment = self._synthesize_assessment(operation, response)

        self.logger.info(
            "operation_risk_assessed",
            operation_type=operation.operation_type.value,
            risk_level=assessment.risk_level.value,
            consensus_strength=assessment.consensus_strength,
            unanimous=assessment.unanimous,
        )

        return assessment

    def _build_assessment_prompt(
        self, operation: Operation, additional_context: Optional[str]
    ) -> str:
        """Build comprehensive risk assessment prompt.

        Args:
            operation: Operation to assess
            additional_context: Optional additional context

        Returns:
            Formatted prompt for multi-agent analysis
        """
        context_str = (
            f"\n\nAdditional Context:\n{additional_context}"
            if additional_context
            else ""
        )

        return f"""Assess the risk of this operation from your perspective as an AI assistant:

**Operation Type**: {operation.operation_type.value}
**Description**: {operation.description}
**Files Affected**: {len(operation.files)} file(s)
{f"**File List**: {', '.join(operation.files[:10])}" if operation.files else ""}
{"..." if len(operation.files) > 10 else ""}
**Changes Summary**: {operation.changes_summary}
**Scope**: {operation.scope}
**Complexity**: {operation.complexity}/10
{f"**Justification**: {operation.justification}" if operation.justification else ""}{context_str}

Please evaluate this operation and provide:

1. **Risk Level**: Choose ONE of: LOW, MEDIUM, HIGH, or CRITICAL
   - LOW: Safe operation with minimal risk
   - MEDIUM: Some risk, requires careful monitoring
   - HIGH: Significant risk, requires approval
   - CRITICAL: Dangerous operation, should be blocked

2. **Potential Impacts**: What could go wrong? List specific failure scenarios.

3. **Blast Radius**: If this fails, what's the scope of impact? (e.g., single user, all users, system-wide, data loss)

4. **Hidden Dependencies**: Are there implicit dependencies or assumptions that could cause issues?

5. **Rollback Complexity**: How difficult would it be to undo this operation?
   - EASY: Simple revert
   - MODERATE: Some manual steps required
   - DIFFICULT: Complex rollback with potential data loss
   - IRREVERSIBLE: Cannot be undone

6. **Reasoning**: Explain your risk assessment in 2-3 sentences.

Format your response clearly with these sections. Be specific and thorough."""

    def _synthesize_assessment(
        self, operation: Operation, response: MultiAgentResponse
    ) -> RiskAssessment:
        """Synthesize risk assessment from multi-agent responses.

        Args:
            operation: Operation being assessed
            response: Multi-agent response

        Returns:
            Synthesized RiskAssessment
        """
        # Extract risk votes from each provider
        provider_votes = {}
        for provider, provider_response in response.responses.items():
            risk_level = self._extract_risk_level(provider_response)
            provider_votes[provider] = risk_level

        # Build consensus using safety-first approach
        consensus_result = self._build_consensus(provider_votes)

        # Extract additional insights
        potential_impacts = self._extract_impacts(response)
        hidden_dependencies = self._extract_dependencies(response)
        rollback_complexity = self._extract_rollback_complexity(response)
        blast_radius = self._extract_blast_radius(response)

        # Build comprehensive rationale
        rationale = self._build_rationale(response, consensus_result, provider_votes)

        return RiskAssessment(
            operation=operation,
            risk_level=consensus_result["level"],
            consensus_strength=consensus_result["consensus_strength"],
            provider_votes=provider_votes,
            rationale=rationale,
            potential_impacts=potential_impacts,
            hidden_dependencies=hidden_dependencies,
            rollback_complexity=rollback_complexity,
            blast_radius=blast_radius,
            unanimous=consensus_result["unanimous"],
        )

    def _extract_risk_level(self, response: str) -> str:
        """Extract risk level from provider response.

        Args:
            response: Provider's response text

        Returns:
            Risk level string (LOW, MEDIUM, HIGH, or CRITICAL)
        """
        response_upper = response.upper()

        # Check in order of severity (most conservative first)
        if "CRITICAL" in response_upper or "DANGEROUS" in response_upper:
            return "CRITICAL"
        elif "HIGH" in response_upper and "RISK" in response_upper:
            return "HIGH"
        elif "MEDIUM" in response_upper:
            return "MEDIUM"
        else:
            return "LOW"

    def _build_consensus(self, provider_votes: Dict[str, str]) -> Dict[str, Any]:
        """Build consensus from provider votes using safety-first approach.

        Args:
            provider_votes: Dict of provider -> risk level

        Returns:
            Dict with consensus details
        """
        if not provider_votes:
            return {
                "level": RiskLevel.CRITICAL,
                "consensus_strength": 1.0,
                "unanimous": True,
            }

        vote_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
        for vote in provider_votes.values():
            vote_counts[vote] += 1

        total_votes = len(provider_votes)

        # Use most conservative risk level (safety-first)
        # If any provider says CRITICAL, consensus is CRITICAL
        for risk_str in reversed(self.RISK_HIERARCHY):
            if vote_counts[risk_str] > 0:
                consensus_level = RiskLevel(risk_str.lower())
                consensus_strength = vote_counts[risk_str] / total_votes
                unanimous = consensus_strength == 1.0
                break
        else:
            consensus_level = RiskLevel.LOW
            consensus_strength = 1.0
            unanimous = True

        return {
            "level": consensus_level,
            "consensus_strength": consensus_strength,
            "unanimous": unanimous,
        }

    def _extract_impacts(self, response: MultiAgentResponse) -> List[str]:
        """Extract potential impacts from responses."""
        impacts = []

        for provider, provider_response in response.responses.items():
            # Look for impact/failure sections
            lines = provider_response.split("\n")
            in_impacts = False

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Detect impact section
                if any(
                    keyword in line.lower()
                    for keyword in [
                        "potential impact",
                        "what could go wrong",
                        "failure scenario",
                    ]
                ):
                    in_impacts = True
                    continue

                # Stop at next section
                if in_impacts and any(
                    line.lower().startswith(keyword)
                    for keyword in [
                        "blast radius",
                        "hidden depend",
                        "rollback",
                        "reasoning",
                    ]
                ):
                    in_impacts = False

                # Extract impact items
                if in_impacts and (line.startswith("-") or line.startswith("*")):
                    impact = line.lstrip("-*").strip()
                    if impact and impact not in impacts:
                        impacts.append(impact)

        return impacts[:10]  # Limit to top 10

    def _extract_dependencies(self, response: MultiAgentResponse) -> List[str]:
        """Extract hidden dependencies from responses."""
        dependencies = []

        for provider, provider_response in response.responses.items():
            lines = provider_response.split("\n")
            in_dependencies = False

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                if "hidden depend" in line.lower() or "implicit depend" in line.lower():
                    in_dependencies = True
                    continue

                if in_dependencies and any(
                    line.lower().startswith(keyword)
                    for keyword in ["rollback", "reasoning", "risk level", "blast"]
                ):
                    in_dependencies = False

                if in_dependencies and (line.startswith("-") or line.startswith("*")):
                    dep = line.lstrip("-*").strip()
                    if dep and dep not in dependencies:
                        dependencies.append(dep)

        return dependencies[:10]

    def _extract_rollback_complexity(self, response: MultiAgentResponse) -> str:
        """Extract rollback complexity assessment."""
        for provider, provider_response in response.responses.items():
            if "IRREVERSIBLE" in provider_response.upper():
                return "IRREVERSIBLE"
            elif (
                "DIFFICULT" in provider_response.upper()
                and "ROLLBACK" in provider_response.upper()
            ):
                return "DIFFICULT"
            elif (
                "MODERATE" in provider_response.upper()
                and "ROLLBACK" in provider_response.upper()
            ):
                return "MODERATE"
            elif (
                "EASY" in provider_response.upper()
                and "ROLLBACK" in provider_response.upper()
            ):
                return "EASY"

        return "MODERATE"  # Default assumption

    def _extract_blast_radius(self, response: MultiAgentResponse) -> str:
        """Extract blast radius description."""
        for provider, provider_response in response.responses.items():
            lines = provider_response.split("\n")
            for i, line in enumerate(lines):
                if "blast radius" in line.lower():
                    # Get next non-empty line
                    for j in range(i + 1, min(i + 5, len(lines))):
                        next_line = lines[j].strip()
                        if next_line and not next_line.startswith("#"):
                            return next_line.lstrip("-*").strip()

        return "Unknown"

    def _build_rationale(
        self,
        response: MultiAgentResponse,
        consensus: Dict[str, Any],
        votes: Dict[str, str],
    ) -> str:
        """Build comprehensive rationale from all responses.

        Args:
            response: Multi-agent response
            consensus: Consensus result
            votes: Provider votes

        Returns:
            Comprehensive rationale string
        """
        rationale_parts = [
            f"Risk Level: {consensus['level'].value.upper()} (Consensus: {consensus['consensus_strength']:.0%})",
            f"\nProvider Votes: {', '.join(f'{p}: {v}' for p, v in votes.items())}",
            "\nKey Concerns:",
        ]

        # Extract key reasoning from each provider
        for provider, provider_response in response.responses.items():
            lines = provider_response.split("\n")
            for i, line in enumerate(lines):
                if "reasoning" in line.lower():
                    # Get next few lines
                    reasoning_lines = []
                    for j in range(i + 1, min(i + 5, len(lines))):
                        next_line = lines[j].strip()
                        if next_line and not next_line.startswith("#"):
                            reasoning_lines.append(next_line)
                    if reasoning_lines:
                        rationale_parts.append(
                            f"\n- {provider.upper()}: {' '.join(reasoning_lines[:2])}"
                        )
                    break

        return "\n".join(rationale_parts)
