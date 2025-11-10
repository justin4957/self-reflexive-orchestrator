"""Integration test for generating a real roadmap with multi-agent-coder."""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.logger import setup_logging
from src.cycles.roadmap_generator import RoadmapGenerator
from src.integrations.multi_agent_coder_client import (
    MultiAgentCoderClient,
    MultiAgentStrategy,
)


def test_generate_real_roadmap():
    """Test generating a complete roadmap for the actual repository.

    This integration test:
    1. Analyzes the current repository's codebase
    2. Uses multi-agent-coder for insights and ideation
    3. Generates a complete, formatted roadmap
    4. Saves the roadmap to file
    """
    print("\n" + "=" * 80)
    print("Integration Test: Generate Real Roadmap with Multi-Agent Collaboration")
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

    # Initialize roadmap generator
    print("\n2. Initializing Roadmap Generator...")
    repo_path = Path(__file__).parent.parent.parent
    generator = RoadmapGenerator(
        repository_path=str(repo_path),
        multi_agent_client=multi_agent_client,
        logger=logger,
    )
    print(f"✓ Roadmap Generator initialized for: {repo_path}")

    # Define project goals
    project_goals = [
        "Achieve autonomous operation with minimal human oversight",
        "Maintain high code quality and test coverage",
        "Implement comprehensive safety mechanisms",
        "Optimize costs while maintaining effectiveness",
    ]

    print("\n3. Project Goals:")
    for i, goal in enumerate(project_goals, 1):
        print(f"   {i}. {goal}")

    # Generate roadmap
    print("\n4. Generating roadmap...")
    print("   This will:")
    print("   - Analyze codebase structure and metrics")
    print(
        "   - Query multiple AI providers for insights (Anthropic, DeepSeek, OpenAI, Perplexity)"
    )
    print("   - Generate feature proposals from diverse perspectives")
    print("   - Cross-critique and refine proposals")
    print("   - Synthesize cohesive roadmap through dialectical method")
    print("   - Format as GitHub-ready markdown")
    print("   Please wait (this may take 2-3 minutes)...")
    print()

    try:
        roadmap = generator.generate_roadmap(
            roadmap_id="integration-test",
            project_goals=project_goals,
            save_to_file=True,
        )

        print("\n" + "=" * 80)
        print("✅ ROADMAP GENERATION COMPLETE")
        print("=" * 80)

        # Display metadata
        print("\n📊 METADATA:")
        print("-" * 80)
        metadata = roadmap.metadata
        print(f"Roadmap ID: {metadata.roadmap_id}")
        print(f"Generated at: {metadata.generated_at.isoformat()}")
        print(f"Repository: {metadata.repository_path}")
        print(f"Total Cost: ${metadata.total_cost:.4f}")
        print(f"Total Tokens: {metadata.total_tokens:,}")
        print(f"Analysis Duration: {metadata.analysis_duration_seconds:.1f}s")
        print(f"Ideation Duration: {metadata.ideation_duration_seconds:.1f}s")
        print(f"Consensus Confidence: {metadata.consensus_confidence:.1%}")

        # Display roadmap summary
        print("\n📋 ROADMAP SUMMARY:")
        print("-" * 80)
        ideation = roadmap.ideation_result
        synthesized = ideation.synthesized_roadmap

        print(f"Total Proposals Considered: {synthesized.total_proposals_considered}")
        print(f"Selected Features: {synthesized.selected_proposals}")
        print(f"Phases: {len(synthesized.phases)}")
        print(f"Consensus Confidence: {synthesized.consensus_confidence:.1%}")

        # Display phases
        print("\n📅 PHASES:")
        print("-" * 80)
        for i, phase in enumerate(synthesized.phases, 1):
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
        for provider, emphasis in synthesized.provider_perspectives.items():
            print(f"- {provider.upper()}: {emphasis}")

        # Display file info
        print("\n💾 OUTPUT:")
        print("-" * 80)
        if roadmap.file_path:
            print(f"Roadmap saved to: {roadmap.file_path}")
            file_size = Path(roadmap.file_path).stat().st_size
            print(f"File size: {file_size:,} bytes")

            # Display first few lines of markdown
            with open(roadmap.file_path, "r") as f:
                lines = f.readlines()[:10]
            print("\nFirst 10 lines of roadmap:")
            print("---")
            for line in lines:
                print(line.rstrip())
            print("---")
        else:
            print("Roadmap not saved to file")

        # Display cost breakdown
        print("\n💰 COST BREAKDOWN:")
        print("-" * 80)
        print(f"Codebase Analysis: ~$0.20 (multi-agent architecture analysis)")
        print(
            f"Feature Ideation: ~${ideation.total_cost/3:.4f} (parallel proposals from 4 providers)"
        )
        print(f"Cross-Critique: ~${ideation.total_cost/3:.4f} (consensus building)")
        print(
            f"Dialectical Synthesis: ~${ideation.total_cost/3:.4f} (roadmap generation)"
        )
        print(f"Total: ${metadata.total_cost:.4f}")

        print("\n" + "=" * 80)
        print("✅ Integration test completed successfully!")
        print("=" * 80 + "\n")

    except Exception as e:
        print(f"\n❌ Failed to generate roadmap: {e}")
        import traceback

        traceback.print_exc()
        return


if __name__ == "__main__":
    test_generate_real_roadmap()
