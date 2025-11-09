"""Integration test for analyzing a real GitHub issue with multi-agent-coder."""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.integrations.multi_agent_coder_client import (
    MultiAgentCoderClient,
    MultiAgentStrategy,
)
from src.analyzers.issue_analyzer import IssueAnalyzer
from src.integrations.github_client import GitHubClient
from src.core.logger import setup_logging


def test_analyze_real_github_issue():
    """Test analyzing a real GitHub issue from this repository.

    This integration test:
    1. Connects to GitHub
    2. Fetches issue #2 from self-reflexive-orchestrator
    3. Analyzes it using multi-agent-coder
    4. Prints the analysis results
    """
    print("\n" + "=" * 80)
    print("Integration Test: Analyze Real GitHub Issue with Multi-Agent-Coder")
    print("=" * 80 + "\n")

    # Setup logging
    logger = setup_logging()

    # Check for required environment variables
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        print("⚠️  GITHUB_TOKEN not found in environment")
        print("Skipping integration test (requires GitHub access)")
        return

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

    # Initialize clients
    print("\n1. Initializing GitHub client...")
    github_client = GitHubClient(
        token=github_token,
        repository="justin4957/self-reflexive-orchestrator",
        logger=logger,
    )
    print("✓ GitHub client initialized")

    print("\n2. Initializing Multi-Agent-Coder client...")
    multi_agent_client = MultiAgentCoderClient(
        multi_agent_coder_path=str(multi_agent_path),
        logger=logger,
        default_strategy=MultiAgentStrategy.ALL,
    )
    print("✓ Multi-Agent-Coder client initialized")

    print("\n3. Initializing Issue Analyzer...")
    analyzer = IssueAnalyzer(
        multi_agent_client=multi_agent_client,
        logger=logger,
        max_complexity_threshold=7,
    )
    print("✓ Issue Analyzer initialized")

    # Fetch a real issue
    print("\n4. Fetching issue #2 from GitHub...")
    try:
        issue = github_client.get_issue(2)
        print(f"✓ Fetched issue: #{issue.number} - {issue.title}")
        print(f"  Labels: {[label.name for label in issue.labels]}")
        print(f"  Body preview: {issue.body[:200] if issue.body else 'No body'}...")
    except Exception as e:
        print(f"❌ Failed to fetch issue: {e}")
        return

    # Analyze the issue
    print("\n5. Analyzing issue with multi-agent-coder...")
    print("   This will query multiple AI providers (Anthropic, DeepSeek, etc.)")
    print("   Please wait...")

    try:
        analysis = analyzer.analyze_issue(issue)

        print("\n" + "=" * 80)
        print("ANALYSIS RESULTS")
        print("=" * 80 + "\n")

        print(f"Issue Number: #{analysis.issue_number}")
        print(f"Issue Type: {analysis.issue_type.value}")
        print(f"Complexity Score: {analysis.complexity_score}/10")
        print(f"Actionable: {'Yes' if analysis.is_actionable else 'No'}")
        print(f"Actionability Reason: {analysis.actionability_reason}")
        print(f"Consensus Confidence: {analysis.consensus_confidence:.2%}")

        print(f"\nKey Requirements ({len(analysis.key_requirements)}):")
        for i, req in enumerate(analysis.key_requirements, 1):
            print(f"  {i}. {req}")

        if analysis.affected_files:
            print(f"\nAffected Files ({len(analysis.affected_files)}):")
            for file in analysis.affected_files[:5]:
                print(f"  - {file}")

        if analysis.risks:
            print(f"\nRisks ({len(analysis.risks)}):")
            for i, risk in enumerate(analysis.risks, 1):
                print(f"  {i}. {risk}")

        print(f"\nRecommended Approach:")
        print(f"  {analysis.recommended_approach[:200]}...")

        print(f"\nProvider Analyses:")
        for provider, text in analysis.provider_analyses.items():
            print(f"  {provider.upper()}: {len(text)} characters")

        print(f"\nCost Metrics:")
        print(f"  Total Tokens: {analysis.total_tokens:,}")
        print(f"  Total Cost: ${analysis.total_cost:.4f}")

        print(f"\nAnalysis Success: {'✓' if analysis.analysis_success else '❌'}")

        # Print analyzer statistics
        print("\n" + "=" * 80)
        print("ANALYZER STATISTICS")
        print("=" * 80 + "\n")

        stats = analyzer.get_statistics()
        print(f"Total Analyses: {stats['analyses_performed']}")
        print(f"Actionable Count: {stats['actionable_count']}")
        print(f"Actionable %: {stats['actionable_percentage']:.1f}%")

        multi_stats = stats["multi_agent_stats"]
        print(f"\nMulti-Agent-Coder Stats:")
        print(f"  Total Calls: {multi_stats['total_calls']}")
        print(f"  Total Tokens: {multi_stats['total_tokens']:,}")
        print(f"  Total Cost: ${multi_stats['total_cost']:.4f}")
        print(f"  Avg Cost/Call: ${multi_stats['average_cost_per_call']:.4f}")
        print(f"  Provider Usage: {multi_stats['provider_usage']}")

        print("\n" + "=" * 80)
        print("✓ Integration test completed successfully!")
        print("=" * 80 + "\n")

    except Exception as e:
        print(f"\n❌ Analysis failed: {e}")
        import traceback

        traceback.print_exc()
        raise


if __name__ == "__main__":
    test_analyze_real_github_issue()
