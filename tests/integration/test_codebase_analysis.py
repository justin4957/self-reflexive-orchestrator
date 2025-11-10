"""Integration test for analyzing a real codebase with multi-agent-coder."""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.analyzers.codebase_analyzer import CodebaseAnalyzer
from src.analyzers.multi_agent_analyzer import MultiAgentAnalyzer
from src.core.logger import setup_logging
from src.integrations.multi_agent_coder_client import (
    MultiAgentCoderClient,
    MultiAgentStrategy,
)


def test_analyze_real_codebase():
    """Test analyzing a real codebase with multi-agent-coder.

    This integration test:
    1. Analyzes the current repository's codebase structure
    2. Uses multi-agent-coder to get insights from multiple AI perspectives
    3. Builds consensus on architecture, technical debt, and improvements
    4. Prints the comprehensive analysis results
    """
    print("\n" + "=" * 80)
    print("Integration Test: Analyze Real Codebase with Multi-Agent-Coder")
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

    # Initialize codebase analyzer
    print("\n1. Initializing Codebase Analyzer...")
    repo_path = Path(__file__).parent.parent.parent
    codebase_analyzer = CodebaseAnalyzer(
        repository_path=str(repo_path),
        logger=logger,
    )
    print(f"✓ Codebase Analyzer initialized for: {repo_path}")

    # Analyze codebase structure
    print("\n2. Analyzing codebase structure and metrics...")
    print("   Scanning files, extracting metrics, detecting patterns...")
    try:
        codebase_analysis = codebase_analyzer.analyze()
        print(f"✓ Codebase analysis complete")
        print(f"  Total files: {codebase_analysis.metrics.total_files}")
        print(f"  Total lines: {codebase_analysis.metrics.total_lines:,}")
        print(f"  Languages: {', '.join(codebase_analysis.metrics.languages.keys())}")
        print(
            f"  Package managers: {', '.join(codebase_analysis.dependencies.package_managers)}"
        )
        print(f"  Has tests: {codebase_analysis.patterns.get('has_tests', False)}")
        print(
            f"  Has documentation: {codebase_analysis.patterns.get('has_documentation', False)}"
        )
    except Exception as e:
        print(f"❌ Failed to analyze codebase: {e}")
        import traceback

        traceback.print_exc()
        return

    # Initialize multi-agent client
    print("\n3. Initializing Multi-Agent-Coder client...")
    multi_agent_client = MultiAgentCoderClient(
        multi_agent_coder_path=str(multi_agent_path),
        logger=logger,
        default_strategy=MultiAgentStrategy.ALL,
    )
    print("✓ Multi-Agent-Coder client initialized")

    # Initialize multi-agent analyzer
    print("\n4. Initializing Multi-Agent Analyzer...")
    multi_agent_analyzer = MultiAgentAnalyzer(
        multi_agent_client=multi_agent_client,
        logger=logger,
    )
    print("✓ Multi-Agent Analyzer initialized")

    # Analyze with multi-agent perspectives
    print("\n5. Analyzing codebase with multi-agent perspectives...")
    print("   This will query multiple AI providers:")
    print("   - Anthropic: Architecture patterns and security")
    print("   - DeepSeek: Performance optimization and code quality")
    print("   - OpenAI: Innovation opportunities and user experience")
    print("   - Perplexity: Industry best practices and standards")
    print("   Please wait...")

    try:
        multi_agent_result = multi_agent_analyzer.analyze_with_multi_agent(
            codebase_analysis=codebase_analysis,
            analysis_id="integration-test",
        )

        print("\n" + "=" * 80)
        print("MULTI-AGENT ANALYSIS RESULTS")
        print("=" * 80)

        # Display provider insights
        print("\n📋 PROVIDER INSIGHTS:")
        print("-" * 80)
        for provider, insight in multi_agent_result.provider_insights.items():
            print(f"\n🤖 {provider.upper()}:")
            if insight.architecture_rating:
                print(f"  Architecture Rating: {insight.architecture_rating}/10")
            if insight.code_quality_rating:
                print(f"  Code Quality Rating: {insight.code_quality_rating}/10")
            if insight.architecture_patterns:
                print(f"  Patterns: {', '.join(insight.architecture_patterns)}")
            if insight.technical_debt_areas:
                print(f"  Tech Debt Areas: {len(insight.technical_debt_areas)}")
                for area in insight.technical_debt_areas[:3]:
                    print(f"    - {area}")
            if insight.improvement_opportunities:
                print(
                    f"  Improvement Opportunities: {len(insight.improvement_opportunities)}"
                )
                for opp in insight.improvement_opportunities[:3]:
                    print(f"    - {opp}")
            if insight.recommendations:
                print(f"  Recommendations: {len(insight.recommendations)}")
                for rec in insight.recommendations[:3]:
                    print(f"    - {rec}")

        # Display consensus
        print("\n" + "=" * 80)
        print("🤝 CONSENSUS INSIGHTS:")
        print("-" * 80)
        consensus = multi_agent_result.consensus

        print(
            f"\nOverall Architecture Rating: {consensus.overall_architecture_rating:.1f}/10"
        )
        print(f"Overall Quality Rating: {consensus.overall_quality_rating:.1f}/10")
        print(f"Consensus Confidence: {consensus.consensus_confidence:.2%}")

        if consensus.consensus_patterns:
            print(f"\nConsensus Patterns:")
            for pattern in consensus.consensus_patterns:
                print(f"  - {pattern}")

        if consensus.top_priorities:
            print(f"\nTop Priorities ({len(consensus.top_priorities)}):")
            for i, priority in enumerate(consensus.top_priorities[:10], 1):
                print(f"  {i}. [{priority['priority'].upper()}] {priority['category']}")
                print(f"     {priority['description']}")
                print(
                    f"     Confidence: {priority['confidence']:.0%} | Mentioned by: {', '.join(priority.get('mentioned_by', []))}"
                )

        if consensus.divergent_opinions:
            print(f"\nDivergent Opinions:")
            for opinion in consensus.divergent_opinions:
                print(f"  - {opinion}")

        # Display statistics
        print("\n" + "=" * 80)
        print("📊 STATISTICS:")
        print("-" * 80)
        print(f"Providers consulted: {len(multi_agent_result.provider_insights)}")
        print(f"Analysis ID: {multi_agent_result.analysis_id}")
        print(f"Analyzed at: {multi_agent_result.analyzed_at.isoformat()}")

        # Display raw codebase metrics summary
        print("\n" + "=" * 80)
        print("📈 CODEBASE METRICS SUMMARY:")
        print("-" * 80)
        metrics = multi_agent_result.raw_codebase_analysis.metrics
        print(f"Files: {metrics.total_files}")
        print(f"Total Lines: {metrics.total_lines:,}")
        print(f"Code Lines: {metrics.total_code_lines:,}")
        print(f"Blank Lines: {metrics.total_blank_lines:,}")
        print(f"Comment Lines: {metrics.total_comment_lines:,}")
        print(f"Average Complexity: {metrics.avg_complexity:.2f}")
        print(
            f"Languages: {', '.join(f'{lang} ({count})' for lang, count in metrics.languages.items())}"
        )

        deps = multi_agent_result.raw_codebase_analysis.dependencies
        print(f"\nDependencies:")
        for manager, packages in deps.dependencies.items():
            print(f"  {manager}: {len(packages)} packages")

        patterns = multi_agent_result.raw_codebase_analysis.patterns
        print(f"\nPatterns Detected:")
        print(f"  Tests: {patterns.get('test_files_count', 0)} test files")
        print(f"  Documentation: {len(patterns.get('documentation_files', []))} docs")
        if patterns.get("frameworks"):
            print(f"  Frameworks: {', '.join(patterns['frameworks'].keys())}")
        print(f"  Architecture: {patterns.get('architecture_pattern', 'Unknown')}")

        print("\n" + "=" * 80)
        print("✅ Integration test completed successfully!")
        print("=" * 80 + "\n")

    except Exception as e:
        print(f"\n❌ Failed to analyze with multi-agent: {e}")
        import traceback

        traceback.print_exc()
        return


if __name__ == "__main__":
    test_analyze_real_codebase()
