"""Integration test for validating roadmaps with multi-agent-coder."""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.cycles.roadmap_validator import RoadmapValidator
from src.cycles.multi_agent_ideation import (
    FeatureProposal,
    ProposalPriority,
    SynthesizedRoadmap,
    IdeationResult,
)
from src.integrations.multi_agent_coder_client import (
    MultiAgentCoderClient,
    MultiAgentStrategy,
)
from src.core.logger import setup_logging


def test_validate_roadmap():
    """Test validating a roadmap with multi-agent collaboration.

    This integration test:
    1. Creates sample roadmap proposals
    2. Uses multi-agent-coder for dialectical validation
    3. Validates through three phases (thesis, antithesis, synthesis)
    4. Filters proposals based on validation results
    5. Generates refined roadmap with validated features
    """
    print("\n" + "=" * 80)
    print("Integration Test: Validate Roadmap with Multi-Agent Collaboration")
    print("=" * 80 + "\n")

    # Setup logging
    logger = setup_logging()

    # Check for multi_agent_coder executable
    multi_agent_path = (
        Path(__file__).parent.parent.parent.parent
        / "multi_agent_coder"
        / "multi_agent_coder"
    )
    if not multi_agent_path.exists():
        print(f"⚠️  multi_agent_coder not found at: {multi_agent_path}")
        print("Skipping integration test (requires multi_agent_coder to be built)")
        return

    print(f"✓ Found multi_agent_coder at: {multi_agent_path}")

    # Initialize multi-agent client
    print("\n1. Initializing Multi-Agent-Coder client...")
    multi_agent_client = MultiAgentCoderClient(
        multi_agent_coder_path=str(multi_agent_path),
        logger=logger,
        default_strategy=MultiAgentStrategy.ALL,
    )
    print("✓ Multi-Agent-Coder client initialized")

    # Initialize roadmap validator
    print("\n2. Initializing Roadmap Validator...")
    validator = RoadmapValidator(
        multi_agent_client=multi_agent_client,
        logger=logger,
        min_confidence=0.8,
    )
    print("✓ Roadmap Validator initialized")

    # Create sample proposals
    print("\n3. Creating sample roadmap proposals...")
    proposals = [
        FeatureProposal(
            id="proposal-1",
            title="Implement Comprehensive Error Handling",
            description="Add structured error handling throughout the application with proper logging and recovery mechanisms.",
            provider="anthropic",
            value_proposition="Reduce production errors by 40% and improve debugging efficiency",
            complexity_estimate=6,
            priority=ProposalPriority.HIGH,
            dependencies=["logging-system"],
            success_metrics=[
                "Error rate < 1%",
                "Mean time to recovery < 5 minutes",
            ],
            estimated_effort="2-3 weeks",
            category="reliability",
        ),
        FeatureProposal(
            id="proposal-2",
            title="Add Redis Caching Layer",
            description="Implement Redis caching for frequently accessed data to improve response times.",
            provider="deepseek",
            value_proposition="Improve response times by 50% for common queries",
            complexity_estimate=7,
            priority=ProposalPriority.MEDIUM,
            dependencies=["redis-setup"],
            success_metrics=[
                "Average response time < 100ms",
                "Cache hit rate > 80%",
            ],
            estimated_effort="3-4 weeks",
            category="performance",
        ),
        FeatureProposal(
            id="proposal-3",
            title="Implement User Authentication with OAuth",
            description="Add OAuth-based authentication supporting Google, GitHub, and Microsoft providers.",
            provider="openai",
            value_proposition="Improve user experience with single sign-on and reduce password management burden",
            complexity_estimate=8,
            priority=ProposalPriority.HIGH,
            dependencies=["user-model", "session-management"],
            success_metrics=[
                "OAuth integration for 3 providers",
                "Login success rate > 95%",
            ],
            estimated_effort="4-5 weeks",
            category="security",
        ),
        FeatureProposal(
            id="proposal-4",
            title="Add API Rate Limiting",
            description="Implement rate limiting to prevent API abuse and ensure fair usage.",
            provider="perplexity",
            value_proposition="Protect infrastructure from abuse and ensure consistent performance for all users",
            complexity_estimate=5,
            priority=ProposalPriority.MEDIUM,
            dependencies=["redis-setup"],
            success_metrics=[
                "Rate limit violations < 0.1%",
                "Zero service degradation from abuse",
            ],
            estimated_effort="1-2 weeks",
            category="security",
        ),
    ]

    print(f"✓ Created {len(proposals)} proposals:")
    for p in proposals:
        print(f"   - [{p.priority.value.upper()}] {p.title} ({p.provider})")

    # Create sample roadmap
    roadmap = SynthesizedRoadmap(
        phases=[
            {
                "name": "Phase 1: Foundation",
                "timeline": "4-6 weeks",
                "features": [
                    {
                        "id": "proposal-1",
                        "title": "Implement Comprehensive Error Handling",
                        "priority": "high",
                        "complexity": 6,
                    },
                    {
                        "id": "proposal-4",
                        "title": "Add API Rate Limiting",
                        "priority": "medium",
                        "complexity": 5,
                    },
                ],
            },
            {
                "name": "Phase 2: Enhancement",
                "timeline": "6-8 weeks",
                "features": [
                    {
                        "id": "proposal-2",
                        "title": "Add Redis Caching Layer",
                        "priority": "medium",
                        "complexity": 7,
                    },
                    {
                        "id": "proposal-3",
                        "title": "Implement User Authentication with OAuth",
                        "priority": "high",
                        "complexity": 8,
                    },
                ],
            },
        ],
        consensus_confidence=0.85,
        total_proposals_considered=8,
        selected_proposals=4,
        provider_perspectives={
            "anthropic": "Security and reliability focus",
            "deepseek": "Performance optimization",
            "openai": "User experience enhancement",
            "perplexity": "Best practices alignment",
        },
        synthesis_notes="Balanced roadmap across all perspectives",
    )

    ideation_result = IdeationResult(
        proposals=proposals,
        critiques={},
        synthesized_roadmap=roadmap,
        total_cost=0.5,
        total_tokens=5000,
        duration_seconds=120.0,
    )

    # Define project goals
    project_goals = [
        "Achieve high reliability and uptime (99.9%)",
        "Provide excellent user experience",
        "Maintain strong security posture",
        "Optimize performance for scale",
    ]

    print("\n4. Project Goals:")
    for i, goal in enumerate(project_goals, 1):
        print(f"   {i}. {goal}")

    # Validate roadmap
    print("\n5. Validating roadmap...")
    print("   This will:")
    print("   - Phase 1 (THESIS): Query all providers for initial analysis")
    print("   - Phase 2 (ANTITHESIS): Use dialectical strategy for critical analysis")
    print("   - Phase 3 (SYNTHESIS): Synthesize refined recommendations")
    print("   - Parse validation results and filter proposals")
    print("   - Generate refined roadmap with validated features")
    print("   Please wait (this may take 1-2 minutes)...")
    print()

    try:
        validated_roadmap = validator.validate_roadmap(
            ideation_result=ideation_result,
            project_goals=project_goals,
        )

        print("\n" + "=" * 80)
        print("✅ ROADMAP VALIDATION COMPLETE")
        print("=" * 80)

        # Display validation results
        print("\n📊 VALIDATION RESULTS:")
        print("-" * 80)
        print(f"Overall Confidence: {validated_roadmap.overall_confidence:.1%}")
        print(
            f"Dialectical Consensus: {validated_roadmap.dialectical_validation.consensus_confidence:.1%}"
        )
        print(f"Total Cost: ${validated_roadmap.total_cost:.4f}")
        print(f"Total Tokens: {validated_roadmap.total_tokens:,}")
        print(f"Duration: {validated_roadmap.duration_seconds:.1f}s")

        # Display proposal decisions
        print("\n📋 PROPOSAL DECISIONS:")
        print("-" * 80)
        print(f"✅ Approved: {len(validated_roadmap.approved_proposals)}")
        print(f"⚠️  Needs Revision: {len(validated_roadmap.needs_revision)}")
        print(f"❌ Rejected: {len(validated_roadmap.rejected_proposals)}")

        # Display approved proposals
        if validated_roadmap.approved_proposals:
            print("\n✅ APPROVED PROPOSALS:")
            print("-" * 80)
            for proposal in validated_roadmap.approved_proposals:
                validation = validated_roadmap.validated_proposals.get(proposal.id)
                confidence = validation.confidence if validation else 0.0
                decision = validation.decision.value if validation else "unknown"
                print(
                    f"\n{proposal.id}: {proposal.title} [{decision.upper()}] (confidence: {confidence:.1%})"
                )
                if validation and validation.strengths:
                    print("  Strengths:")
                    for strength in validation.strengths[:3]:
                        print(f"    - {strength}")
                if validation and validation.suggestions:
                    print("  Suggestions:")
                    for suggestion in validation.suggestions[:3]:
                        print(f"    - {suggestion}")

        # Display rejected proposals
        if validated_roadmap.rejected_proposals:
            print("\n❌ REJECTED PROPOSALS:")
            print("-" * 80)
            for proposal in validated_roadmap.rejected_proposals:
                validation = validated_roadmap.validated_proposals.get(proposal.id)
                confidence = validation.confidence if validation else 0.0
                print(
                    f"\n{proposal.id}: {proposal.title} (confidence: {confidence:.1%})"
                )
                if validation and validation.concerns:
                    print("  Concerns:")
                    for concern in validation.concerns[:3]:
                        print(f"    - {concern}")
                if validation and validation.risks:
                    print("  Risks:")
                    for risk in validation.risks[:3]:
                        print(f"    - {risk}")

        # Display needs revision
        if validated_roadmap.needs_revision:
            print("\n⚠️  NEEDS REVISION:")
            print("-" * 80)
            for proposal in validated_roadmap.needs_revision:
                validation = validated_roadmap.validated_proposals.get(proposal.id)
                print(f"\n{proposal.id}: {proposal.title}")
                if validation and validation.suggestions:
                    print("  Suggestions:")
                    for suggestion in validation.suggestions[:3]:
                        print(f"    - {suggestion}")

        # Display refined phases
        print("\n📅 REFINED ROADMAP PHASES:")
        print("-" * 80)
        for i, phase in enumerate(validated_roadmap.refined_phases, 1):
            phase_name = phase.get("name", f"Phase {i}")
            timeline = phase.get("timeline", "TBD")
            features = phase.get("features", [])
            print(f"\n{i}. {phase_name}")
            print(f"   Timeline: {timeline}")
            print(f"   Features: {len(features)}")
            for j, feature in enumerate(features, 1):
                title = feature.get("title", "Untitled")
                priority = feature.get("priority", "medium")
                print(f"   {i}.{j} [{priority.upper()}] {title}")

        # Display dialectical validation summary
        print("\n🔄 DIALECTICAL VALIDATION:")
        print("-" * 80)
        dialectical = validated_roadmap.dialectical_validation
        print(f"\n📝 Thesis (Initial Analysis):")
        print(f"   {len(dialectical.thesis)} characters")
        print(f"\n🔍 Antithesis (Critical Analysis):")
        print(f"   {len(dialectical.antithesis)} characters")
        print(f"\n✨ Synthesis (Refined Recommendations):")
        print(f"   {len(dialectical.synthesis)} characters")
        print(f"\n📊 Consensus Confidence: {dialectical.consensus_confidence:.1%}")

        # Display cost breakdown
        print("\n💰 COST BREAKDOWN:")
        print("-" * 80)
        thesis_cost = validated_roadmap.total_cost * 0.33
        antithesis_cost = validated_roadmap.total_cost * 0.33
        synthesis_cost = validated_roadmap.total_cost * 0.34
        print(f"Phase 1 (Thesis): ~${thesis_cost:.4f}")
        print(f"Phase 2 (Antithesis): ~${antithesis_cost:.4f}")
        print(f"Phase 3 (Synthesis): ~${synthesis_cost:.4f}")
        print(f"Total: ${validated_roadmap.total_cost:.4f}")

        print("\n" + "=" * 80)
        print("✅ Integration test completed successfully!")
        print("=" * 80 + "\n")

    except Exception as e:
        print(f"\n❌ Failed to validate roadmap: {e}")
        import traceback

        traceback.print_exc()
        return


if __name__ == "__main__":
    test_validate_roadmap()
