"""Unit tests for RoadmapGenerator."""

import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from src.analyzers.codebase_analyzer import (CodebaseAnalysis, CodebaseMetrics,
                                             DependencyInfo)
from src.analyzers.multi_agent_analyzer import (ConsensusInsights,
                                                MultiAgentAnalysisResult,
                                                ProviderInsight)
from src.core.logger import AuditLogger
from src.cycles.multi_agent_ideation import (FeatureProposal, IdeationResult,
                                             ProposalCritique,
                                             ProposalPriority,
                                             SynthesizedRoadmap)
from src.cycles.roadmap_generator import (GeneratedRoadmap, RoadmapGenerator,
                                          RoadmapMetadata)
from src.integrations.multi_agent_coder_client import MultiAgentCoderClient


class TestRoadmapGenerator(unittest.TestCase):
    """Test cases for RoadmapGenerator."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.multi_agent_client = Mock(spec=MultiAgentCoderClient)

        # Create temporary repository
        self.test_repo = tempfile.mkdtemp()
        self.test_path = Path(self.test_repo)

        # Create basic structure
        (self.test_path / "src").mkdir()
        (self.test_path / "src" / "main.py").write_text("print('test')")

        self.generator = RoadmapGenerator(
            repository_path=str(self.test_path),
            multi_agent_client=self.multi_agent_client,
            logger=self.logger,
        )

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.test_repo)

    def test_initialization(self):
        """Test generator initialization."""
        self.assertEqual(
            self.generator.repository_path.resolve(), self.test_path.resolve()
        )
        self.assertTrue(self.generator.output_dir.exists())
        self.assertIsNotNone(self.generator.codebase_analyzer)
        self.assertIsNotNone(self.generator.multi_agent_analyzer)
        self.assertIsNotNone(self.generator.ideation_engine)

    def test_output_directory_creation(self):
        """Test that output directory is created."""
        expected_dir = self.test_path / "roadmaps"
        self.assertTrue(expected_dir.exists())

    def test_format_executive_summary(self):
        """Test formatting executive summary."""
        codebase_analysis = CodebaseAnalysis(
            repository_path="/test",
            analyzed_at=datetime.now(timezone.utc),
            metrics=CodebaseMetrics(
                total_files=50,
                total_lines=5000,
                total_code_lines=3500,
                total_blank_lines=750,
                total_comment_lines=750,
                avg_complexity=5.2,
                languages={"python": 40},
                file_types={".py": 40},
            ),
            dependencies=DependencyInfo(
                package_managers=["pip"],
                dependencies={"pip": []},
            ),
            file_structure={},
            file_metrics=[],
            patterns={},
        )

        multi_agent_analysis = MultiAgentAnalysisResult(
            analysis_id="test",
            analyzed_at=datetime.now(timezone.utc),
            provider_insights={"anthropic": ProviderInsight(provider="anthropic")},
            consensus=ConsensusInsights(
                overall_architecture_rating=8.0,
                overall_quality_rating=7.5,
                consensus_patterns=[],
                top_priorities=[],
                consensus_confidence=0.85,
            ),
            raw_codebase_analysis=codebase_analysis,
        )

        ideation_result = IdeationResult(
            proposals=[],
            critiques={},
            synthesized_roadmap=SynthesizedRoadmap(
                phases=[{"name": "Phase 1"}],
                consensus_confidence=0.85,
                total_proposals_considered=10,
                selected_proposals=5,
                provider_perspectives={},
                synthesis_notes="",
            ),
            total_cost=0.5,
            total_tokens=5000,
            duration_seconds=120.0,
        )

        lines = self.generator._format_executive_summary(
            codebase_analysis, multi_agent_analysis, ideation_result
        )

        summary_text = "\n".join(lines)
        self.assertIn("Executive Summary", summary_text)
        self.assertIn("50", summary_text)  # total files
        self.assertIn("5 priority features", summary_text)
        self.assertIn("85%", summary_text)  # consensus

    def test_format_current_state(self):
        """Test formatting current state section."""
        codebase_analysis = CodebaseAnalysis(
            repository_path="/test",
            analyzed_at=datetime.now(timezone.utc),
            metrics=CodebaseMetrics(
                total_files=50,
                total_lines=5000,
                total_code_lines=3500,
                total_blank_lines=750,
                total_comment_lines=750,
                avg_complexity=5.2,
                languages={"python": 40},
                file_types={".py": 40},
            ),
            dependencies=DependencyInfo(
                package_managers=["pip"],
                dependencies={"pip": []},
            ),
            file_structure={},
            file_metrics=[],
            patterns={"has_tests": True, "test_files_count": 15},
        )

        consensus = ConsensusInsights(
            overall_architecture_rating=8.0,
            overall_quality_rating=7.5,
            consensus_patterns=["MVC"],
            top_priorities=[
                {
                    "priority": "high",
                    "category": "improvement",
                    "description": "Add error handling",
                    "confidence": 0.9,
                }
            ],
            consensus_confidence=0.85,
        )

        lines = self.generator._format_current_state(codebase_analysis, consensus)

        state_text = "\n".join(lines)
        self.assertIn("Current State", state_text)
        self.assertIn("50", state_text)  # files
        self.assertIn("8.0/10", state_text)  # architecture rating
        self.assertIn("MVC", state_text)  # pattern

    def test_format_phases(self):
        """Test formatting phases section."""
        phases = [
            {
                "name": "Phase 1: Foundation",
                "timeline": "4-6 weeks",
                "features": [
                    {
                        "id": "test-1",
                        "title": "Add Error Handling",
                        "description": "Comprehensive error handling",
                        "complexity": 6,
                        "priority": "high",
                    }
                ],
            }
        ]

        critiques = {
            "test-1": ProposalCritique(
                proposal_id="test-1",
                strengths=["Well designed"],
                weaknesses=["Complex"],
            )
        }

        lines = self.generator._format_phases(phases, critiques)

        phases_text = "\n".join(lines)
        self.assertIn("Roadmap Phases", phases_text)
        self.assertIn("Phase 1", phases_text)
        self.assertIn("4-6 weeks", phases_text)
        self.assertIn("Add Error Handling", phases_text)
        self.assertIn("Well designed", phases_text)

    def test_format_multi_agent_insights(self):
        """Test formatting multi-agent insights."""
        synthesized = SynthesizedRoadmap(
            phases=[],
            consensus_confidence=0.85,
            total_proposals_considered=10,
            selected_proposals=5,
            provider_perspectives={
                "anthropic": "Security focus",
                "deepseek": "Performance optimization",
            },
            synthesis_notes="Balanced approach across all perspectives",
        )

        multi_agent_analysis = MultiAgentAnalysisResult(
            analysis_id="test",
            analyzed_at=datetime.now(timezone.utc),
            provider_insights={
                "anthropic": ProviderInsight(
                    provider="anthropic",
                    architecture_rating=8,
                    recommendations=["Add monitoring"],
                )
            },
            consensus=ConsensusInsights(
                overall_architecture_rating=8.0,
                overall_quality_rating=7.5,
                consensus_patterns=[],
                top_priorities=[],
                consensus_confidence=0.85,
            ),
            raw_codebase_analysis=Mock(),
        )

        lines = self.generator._format_multi_agent_insights(
            synthesized, multi_agent_analysis
        )

        insights_text = "\n".join(lines)
        self.assertIn("Multi-Agent Insights", insights_text)
        self.assertIn("ANTHROPIC", insights_text)
        self.assertIn("Security focus", insights_text)

    def test_format_implementation_notes(self):
        """Test formatting implementation notes."""
        synthesized = SynthesizedRoadmap(
            phases=[],
            consensus_confidence=0.85,
            total_proposals_considered=10,
            selected_proposals=5,
            provider_perspectives={},
            synthesis_notes="",
        )

        lines = self.generator._format_implementation_notes(synthesized)

        notes_text = "\n".join(lines)
        self.assertIn("Implementation Notes", notes_text)
        self.assertIn("Dependencies", notes_text)
        self.assertIn("Success Metrics", notes_text)

    def test_format_all_proposals(self):
        """Test formatting all proposals appendix."""
        ideation_result = IdeationResult(
            proposals=[
                FeatureProposal(
                    id="test-1",
                    title="Feature 1",
                    description="Description",
                    provider="anthropic",
                    value_proposition="High value",
                    complexity_estimate=6,
                    priority=ProposalPriority.HIGH,
                )
            ],
            critiques={},
            synthesized_roadmap=Mock(),
            total_cost=0.5,
            total_tokens=5000,
            duration_seconds=120.0,
        )

        lines = self.generator._format_all_proposals(ideation_result)

        appendix_text = "\n".join(lines)
        self.assertIn("Appendix", appendix_text)
        self.assertIn("Feature 1", appendix_text)
        self.assertIn("ANTHROPIC", appendix_text)

    def test_save_roadmap(self):
        """Test saving roadmap to file."""
        roadmap_id = "test-roadmap-123"
        content = "# Test Roadmap\n\nThis is a test."

        file_path = self.generator._save_roadmap(roadmap_id, content)

        self.assertTrue(file_path.exists())
        self.assertEqual(file_path.name, f"{roadmap_id}.md")

        # Verify content
        with open(file_path, "r") as f:
            saved_content = f.read()
        self.assertEqual(saved_content, content)

    def test_roadmap_metadata_to_dict(self):
        """Test RoadmapMetadata to_dict conversion."""
        metadata = RoadmapMetadata(
            generated_at=datetime(2025, 1, 10, 12, 0, 0, tzinfo=timezone.utc),
            roadmap_id="test-123",
            repository_path="/test/repo",
            total_cost=0.5,
            total_tokens=5000,
            analysis_duration_seconds=10.5,
            ideation_duration_seconds=120.5,
            consensus_confidence=0.85,
        )

        result = metadata.to_dict()

        self.assertEqual(result["roadmap_id"], "test-123")
        self.assertEqual(result["total_cost"], 0.5)
        self.assertEqual(result["consensus_confidence"], 0.85)

    def test_generated_roadmap_to_dict(self):
        """Test GeneratedRoadmap to_dict conversion."""
        metadata = RoadmapMetadata(
            generated_at=datetime.now(timezone.utc),
            roadmap_id="test-123",
            repository_path="/test",
            total_cost=0.5,
            total_tokens=5000,
            analysis_duration_seconds=10.0,
            ideation_duration_seconds=120.0,
            consensus_confidence=0.85,
        )

        # Create minimal mocks
        codebase_analysis = Mock()
        codebase_analysis.to_dict.return_value = {"test": "data"}

        multi_agent_analysis = Mock()
        multi_agent_analysis.to_dict.return_value = {"test": "data"}

        ideation_result = Mock()
        ideation_result.to_dict.return_value = {"test": "data"}

        roadmap = GeneratedRoadmap(
            metadata=metadata,
            codebase_analysis=codebase_analysis,
            multi_agent_analysis=multi_agent_analysis,
            ideation_result=ideation_result,
            markdown_content="# Test",
            file_path="/test/roadmap.md",
        )

        result = roadmap.to_dict()

        self.assertIn("metadata", result)
        self.assertIn("codebase_analysis", result)
        self.assertIn("markdown_content", result)
        self.assertEqual(result["file_path"], "/test/roadmap.md")


if __name__ == "__main__":
    unittest.main()
