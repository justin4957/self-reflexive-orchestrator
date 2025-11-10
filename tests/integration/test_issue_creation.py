"""Integration test for creating GitHub issues from roadmap."""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.logger import setup_logging
from src.cycles.issue_creator import IssueCreator
from src.cycles.multi_agent_ideation import FeatureProposal, ProposalPriority
from src.cycles.roadmap_validator import (
    DialecticalValidation,
    ProposalValidation,
    SynthesizedRoadmap,
    ValidatedRoadmap,
    ValidationDecision,
)
from src.integrations.github_client import GitHubClient


def test_create_issues():
    """Test creating GitHub issues from validated roadmap.

    This integration test:
    1. Creates sample validated roadmap
    2. Uses GitHub API to create real issues
    3. Tracks created issue numbers
    4. Displays comprehensive results

    NOTE: This test creates REAL issues in the repository!
    Set DRY_RUN=true to skip actual issue creation.
    """
    print("\n" + "=" * 80)
    print("Integration Test: Create GitHub Issues from Roadmap")
    print("=" * 80 + "\n")

    # Check for dry run mode
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"

    if dry_run:
        print("⚠️  DRY RUN MODE - No issues will be created\n")
    else:
        print("⚠️  LIVE MODE - This will create REAL GitHub issues!\n")
        print("Set DRY_RUN=true to skip actual creation.\n")

    # Setup logging
    logger = setup_logging()

    # Check for GitHub token
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        print("⚠️  GITHUB_TOKEN not set")
        print("Set GITHUB_TOKEN environment variable to run this test")
        return

    print("✓ GitHub token found")

    # Get repository
    repository = os.getenv(
        "GITHUB_REPOSITORY", "justin4957/self-reflexive-orchestrator"
    )
    print(f"✓ Repository: {repository}")

    if dry_run:
        print("\n✓ Skipping issue creation (dry run mode)")
        print("\n" + "=" * 80)
        print("✅ Integration test completed (dry run)!")
        print("=" * 80 + "\n")
        return

    # Initialize GitHub client
    print("\n1. Initializing GitHub client...")
    github_client = GitHubClient(
        token=github_token,
        repository=repository,
        logger=logger,
    )
    print("✓ GitHub client initialized")

    # Initialize issue creator
    print("\n2. Initializing Issue Creator...")
    issue_creator = IssueCreator(
        github_client=github_client,
        logger=logger,
        auto_label=True,
        add_bot_approved=True,  # Add bot-approved for testing
    )
    print("✓ Issue Creator initialized")

    # Create sample validated roadmap
    print("\n3. Creating sample validated roadmap...")

    proposals = [
        FeatureProposal(
            id="integration-test-1",
            title="Add Comprehensive Logging System",
            description="Implement structured logging throughout the application with context, log levels, and output formatting.",
            provider="anthropic",
            value_proposition="Improve debugging efficiency and system observability",
            complexity_estimate=5,
            priority=ProposalPriority.HIGH,
            dependencies=[],
            success_metrics=[
                "All critical operations logged",
                "Log levels configurable",
                "Structured output format",
            ],
            estimated_effort="1-2 weeks",
            category="reliability",
        ),
        FeatureProposal(
            id="integration-test-2",
            title="Optimize Database Query Performance",
            description="Analyze and optimize slow database queries, add indexes, and implement query caching.",
            provider="deepseek",
            value_proposition="Reduce average query time by 50%",
            complexity_estimate=7,
            priority=ProposalPriority.MEDIUM,
            dependencies=["caching-layer"],
            success_metrics=[
                "Average query time < 50ms",
                "Database CPU usage < 60%",
                "Cache hit rate > 80%",
            ],
            estimated_effort="3-4 weeks",
            category="performance",
        ),
    ]

    validations = {
        "integration-test-1": ProposalValidation(
            proposal_id="integration-test-1",
            decision=ValidationDecision.APPROVED,
            confidence=0.92,
            strengths=[
                "Clear implementation path",
                "Well-defined success metrics",
                "High value for debugging",
            ],
            concerns=["Need to ensure performance impact is minimal"],
            risks=["Integration with existing code"],
            suggestions=[
                "Use structured logging library (e.g., structlog)",
                "Add log rotation configuration",
            ],
        ),
        "integration-test-2": ProposalValidation(
            proposal_id="integration-test-2",
            decision=ValidationDecision.APPROVED_WITH_CHANGES,
            confidence=0.85,
            strengths=[
                "Significant performance improvement",
                "Measurable success criteria",
            ],
            concerns=[
                "Caching layer dependency needs to be implemented first",
                "Database schema changes may be required",
            ],
            risks=["Query optimization may introduce bugs"],
            suggestions=[
                "Start with query analysis and profiling",
                "Add comprehensive tests before and after",
                "Implement in phases with gradual rollout",
            ],
        ),
    }

    validated_roadmap = ValidatedRoadmap(
        original_roadmap=SynthesizedRoadmap(
            phases=[
                {
                    "name": "Phase 1: Foundation",
                    "timeline": "2-3 weeks",
                    "features": [
                        {
                            "id": "integration-test-1",
                            "title": "Add Comprehensive Logging System",
                        }
                    ],
                },
                {
                    "name": "Phase 2: Optimization",
                    "timeline": "4-5 weeks",
                    "features": [
                        {
                            "id": "integration-test-2",
                            "title": "Optimize Database Query Performance",
                        }
                    ],
                },
            ],
            consensus_confidence=0.88,
            total_proposals_considered=6,
            selected_proposals=2,
            provider_perspectives={
                "anthropic": "Reliability and maintainability focus",
                "deepseek": "Performance optimization",
            },
            synthesis_notes="Balanced approach",
        ),
        validated_proposals=validations,
        dialectical_validation=DialecticalValidation(
            thesis="Initial validation",
            antithesis="Critical analysis",
            synthesis="Refined recommendations",
            consensus_confidence=0.88,
            total_cost=0.12,
            total_tokens=3500,
            duration_seconds=45.0,
        ),
        approved_proposals=proposals,
        rejected_proposals=[],
        needs_revision=[],
        refined_phases=[],
        overall_confidence=0.89,
        total_cost=0.12,
        total_tokens=3500,
        duration_seconds=45.0,
    )

    print(f"✓ Created validated roadmap with {len(proposals)} proposals")

    # Create issues
    print("\n4. Creating GitHub issues...")
    print("   This will create real issues in the repository...")
    print()

    try:
        result = issue_creator.create_issues_from_roadmap(
            validated_roadmap=validated_roadmap,
            only_approved=True,
            skip_existing=True,
        )

        print("\n" + "=" * 80)
        print("✅ ISSUE CREATION COMPLETE")
        print("=" * 80)

        # Display results
        print("\n📊 CREATION RESULTS:")
        print("-" * 80)
        print(f"Total Created: {result.total_created}")
        print(f"Total Skipped: {result.total_skipped}")
        print(f"Total Failed: {result.total_failed}")

        # Display created issues
        if result.created_issues:
            print("\n✅ CREATED ISSUES:")
            print("-" * 80)
            for issue in result.created_issues:
                print(f"\n#{issue.issue_number}: {issue.title}")
                print(f"  URL: {issue.url}")
                print(f"  Proposal ID: {issue.proposal_id}")
                print(f"  Labels: {', '.join(issue.labels)}")

        # Display skipped
        if result.skipped_proposals:
            print("\n⚠️  SKIPPED PROPOSALS:")
            print("-" * 80)
            for proposal_id in result.skipped_proposals:
                print(f"  - {proposal_id}")

        # Display failed
        if result.failed_proposals:
            print("\n❌ FAILED PROPOSALS:")
            print("-" * 80)
            for proposal_id in result.failed_proposals:
                print(f"  - {proposal_id}")

        print("\n" + "=" * 80)
        print("✅ Integration test completed successfully!")
        print("=" * 80 + "\n")

        # Cleanup instructions
        if result.created_issues:
            print("⚠️  CLEANUP INSTRUCTIONS:")
            print("-" * 80)
            print("The following issues were created for testing:")
            for issue in result.created_issues:
                print(f"  - Issue #{issue.issue_number}: {issue.url}")
            print("\nYou may want to close these issues after testing.")
            print("Use: gh issue close <issue_number>")
            print()

    except Exception as e:
        print(f"\n❌ Failed to create issues: {e}")
        import traceback

        traceback.print_exc()
        return


if __name__ == "__main__":
    test_create_issues()
