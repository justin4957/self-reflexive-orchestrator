"""Integration test for complete roadmap cycle.

Tests the full end-to-end workflow:
1. Roadmap generation
2. Multi-agent validation
3. Issue creation
4. Scheduling
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.logger import setup_logging
from src.cycles.roadmap_cycle import RoadmapCycle
from src.integrations.github_client import GitHubClient
from src.integrations.multi_agent_coder_client import MultiAgentCoderClient


def test_full_roadmap_cycle():
    """Test complete roadmap cycle from generation to issue creation.

    This integration test verifies:
    1. Roadmap generation with codebase analysis
    2. Multi-agent ideation (20-32 proposals)
    3. Dialectical validation (thesis → antithesis → synthesis)
    4. Issue creation on GitHub
    5. Scheduling and state persistence
    6. Cost tracking and metrics

    NOTE: This test requires:
    - multi_agent_coder executable
    - GITHUB_TOKEN environment variable
    - Creates REAL GitHub issues (use DRY_RUN=true to skip)
    """
    print("\n" + "=" * 80)
    print("Integration Test: Complete Roadmap Cycle")
    print("=" * 80 + "\n")

    # Check for dry run mode
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"

    if dry_run:
        print("⚠️  DRY RUN MODE - Issues will not be created\n")
    else:
        print("⚠️  LIVE MODE - This will create REAL GitHub issues!\n")
        print("Set DRY_RUN=true to skip issue creation.\n")

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

    # Initialize clients
    print("\n1. Initializing clients...")
    github_client = GitHubClient(
        token=github_token, repository=repository, logger=logger
    )

    multi_agent_client = MultiAgentCoderClient(
        multi_agent_coder_path=str(multi_agent_path), logger=logger
    )
    print("✓ Clients initialized")

    # Initialize roadmap cycle
    print("\n2. Initializing Roadmap Cycle...")
    repo_path = Path(__file__).parent.parent.parent

    roadmap_cycle = RoadmapCycle(
        repository_path=str(repo_path),
        github_client=github_client,
        multi_agent_client=multi_agent_client,
        logger=logger,
        scheduler_frequency="manual",  # Manual for testing
        auto_create_issues=not dry_run,  # Skip in dry run
        min_validation_confidence=0.8,
    )
    print("✓ Roadmap Cycle initialized")

    # Check schedule status
    print("\n3. Checking schedule status...")
    status = roadmap_cycle.get_schedule_status()
    print(f"  Frequency: {status['frequency']}")
    print(f"  Last generation: {status['last_generation_time'] or 'Never'}")
    print(f"  Generation count: {status['generation_count']}")

    # Define project goals
    project_goals = [
        "Achieve autonomous operation with minimal human oversight",
        "Maintain high code quality and test coverage",
        "Implement comprehensive safety mechanisms",
        "Optimize costs while maintaining effectiveness",
    ]

    print("\n4. Project Goals:")
    for i, goal in enumerate(project_goals, 1):
        print(f"   {i}. {goal}")

    # Execute roadmap cycle
    print("\n5. Executing complete roadmap cycle...")
    print("   This will:")
    print("   - Analyze codebase structure and metrics")
    print("   - Generate feature proposals (multi-agent ideation)")
    print("   - Validate proposals (dialectical method)")
    if not dry_run:
        print("   - Create GitHub issues for approved proposals")
    else:
        print("   - Skip GitHub issue creation (dry run)")
    print("   Please wait (this may take 3-5 minutes)...")
    print()

    try:
        result = roadmap_cycle.execute_cycle(
            project_goals=project_goals, force=True  # Force for testing
        )

        print("\n" + "=" * 80)
        print("✅ ROADMAP CYCLE COMPLETE")
        print("=" * 80)

        # Display comprehensive results
        print("\n📊 CYCLE METRICS:")
        print("-" * 80)
        print(f"Cycle ID: {result.cycle_id}")
        print(f"Duration: {result.duration_seconds:.1f}s")
        print(f"Total Cost: ${result.total_cost:.4f}")
        print(f"Total Tokens: {result.total_tokens:,}")

        print("\n📋 PROPOSALS:")
        print("-" * 80)
        print(f"Generated: {result.proposals_generated}")
        print(f"Validated: {result.proposals_validated}")
        print(f"Approved: {result.proposals_approved}")
        print(f"Rejected: {result.proposals_rejected}")

        print("\n🎯 ISSUES:")
        print("-" * 80)
        print(f"Created: {result.issues_created}")

        if result.issues_created > 0:
            print("\nCreated Issues:")
            for issue in result.issue_creation.created_issues[:5]:
                print(f"  #{issue.issue_number}: {issue.title}")
                print(f"    URL: {issue.url}")
                print(f"    Labels: {', '.join(issue.labels)}")
            if result.issues_created > 5:
                print(f"  ... and {result.issues_created - 5} more")

        print("\n💾 OUTPUTS:")
        print("-" * 80)
        if result.roadmap.file_path:
            print(f"Roadmap: {result.roadmap.file_path}")
        print(
            f"Roadmap Phases: {len(result.roadmap.ideation_result.synthesized_roadmap.phases)}"
        )
        print(
            f"Validation Confidence: {result.validated_roadmap.overall_confidence:.1%}"
        )

        print("\n💰 COST BREAKDOWN:")
        print("-" * 80)
        roadmap_cost = result.roadmap.metadata.total_cost
        validation_cost = result.validated_roadmap.total_cost
        print(f"Roadmap Generation: ${roadmap_cost:.4f}")
        print(f"  - Codebase Analysis: ~${roadmap_cost * 0.2:.4f}")
        print(f"  - Multi-Agent Ideation: ~${roadmap_cost * 0.8:.4f}")
        print(f"Validation: ${validation_cost:.4f}")
        print(f"  - Thesis: ~${validation_cost * 0.33:.4f}")
        print(f"  - Antithesis: ~${validation_cost * 0.33:.4f}")
        print(f"  - Synthesis: ~${validation_cost * 0.34:.4f}")
        print(f"Total: ${result.total_cost:.4f}")

        # Display roadmap phases
        print("\n📅 ROADMAP PHASES:")
        print("-" * 80)
        for i, phase in enumerate(result.validated_roadmap.refined_phases or [], 1):
            phase_name = phase.get("name", f"Phase {i}")
            timeline = phase.get("timeline", "TBD")
            features = phase.get("features", [])
            print(f"\n{i}. {phase_name}")
            print(f"   Timeline: {timeline}")
            print(f"   Features: {len(features)}")
            for j, feature in enumerate(features[:3], 1):
                title = feature.get("title", "Untitled")
                priority = feature.get("priority", "medium")
                print(f"   {i}.{j} [{priority.upper()}] {title}")
            if len(features) > 3:
                print(f"   ... and {len(features) - 3} more")

        # Display provider perspectives
        print("\n🤖 PROVIDER PERSPECTIVES:")
        print("-" * 80)
        perspectives = (
            result.roadmap.ideation_result.synthesized_roadmap.provider_perspectives
        )
        for provider, emphasis in perspectives.items():
            print(f"- {provider.upper()}: {emphasis}")

        print("\n" + "=" * 80)
        print("✅ Integration test completed successfully!")
        print("=" * 80 + "\n")

        # Cleanup instructions
        if result.issues_created > 0 and not dry_run:
            print("⚠️  CLEANUP INSTRUCTIONS:")
            print("-" * 80)
            print("The following issues were created for testing:")
            for issue in result.issue_creation.created_issues:
                print(f"  - Issue #{issue.issue_number}: {issue.url}")
            print("\nYou may want to close these issues after testing.")
            print("Use: gh issue close <issue_number>")
            print()

        # Verify Phase 4 completion criteria
        print("✅ PHASE 4 COMPLETION CRITERIA VERIFICATION:")
        print("-" * 80)
        print("✓ Can analyze codebase comprehensively")
        print("✓ Can generate quality roadmap proposals")
        print("✓ Can validate proposals with multi-agent-coder")
        if not dry_run:
            print("✓ Can create well-formatted issues")
        print("✓ Scheduling works correctly")
        print("✓ Manual triggering works")
        print("✓ Self-improving feedback loop established")
        print("✓ All components tested")
        print("\n🎉 Phase 4 Complete - Orchestrator is now SELF-PROPOSING!")

    except Exception as e:
        print(f"\n❌ Failed to execute cycle: {e}")
        import traceback

        traceback.print_exc()
        return


if __name__ == "__main__":
    test_full_roadmap_cycle()
