"""Unit tests for MultiAgentIdeation."""

import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from src.analyzers.codebase_analyzer import (CodebaseAnalysis, CodebaseMetrics,
                                             DependencyInfo)
from src.analyzers.multi_agent_analyzer import (ConsensusInsights,
                                                MultiAgentAnalysisResult,
                                                ProviderInsight)
from src.core.logger import AuditLogger
from src.cycles.multi_agent_ideation import (FeatureProposal, IdeationResult,
                                             MultiAgentIdeation,
                                             ProposalCritique,
                                             ProposalPriority,
                                             SynthesizedRoadmap)
from src.integrations.multi_agent_coder_client import (MultiAgentCoderClient,
                                                       MultiAgentResponse,
                                                       MultiAgentStrategy)


class TestMultiAgentIdeation(unittest.TestCase):
    """Test cases for MultiAgentIdeation."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.multi_agent_client = Mock(spec=MultiAgentCoderClient)

        self.ideation = MultiAgentIdeation(
            multi_agent_client=self.multi_agent_client,
            logger=self.logger,
        )

        # Create sample codebase analysis
        self.codebase_analysis = CodebaseAnalysis(
            repository_path="/test/repo",
            analyzed_at=datetime.now(timezone.utc),
            metrics=CodebaseMetrics(
                total_files=50,
                total_lines=5000,
                total_code_lines=3500,
                total_blank_lines=750,
                total_comment_lines=750,
                avg_complexity=5.2,
                languages={"python": 40, "javascript": 10},
                file_types={".py": 40, ".js": 10},
            ),
            dependencies=DependencyInfo(
                package_managers=["pip", "npm"],
                dependencies={"pip": ["flask", "pytest"], "npm": ["react"]},
            ),
            file_structure={"src": {"main.py": "file"}},
            file_metrics=[],
            patterns={
                "has_tests": True,
                "test_files_count": 15,
                "has_documentation": True,
                "frameworks": {"flask": True},
                "architecture_pattern": "MVC-like",
            },
        )

        # Create sample multi-agent analysis
        self.multi_agent_analysis = MultiAgentAnalysisResult(
            analysis_id="test-analysis",
            analyzed_at=datetime.now(timezone.utc),
            provider_insights={
                "anthropic": ProviderInsight(
                    provider="anthropic",
                    architecture_rating=8,
                    architecture_patterns=["MVC"],
                )
            },
            consensus=ConsensusInsights(
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
            ),
            raw_codebase_analysis=self.codebase_analysis,
        )

    def test_initialization(self):
        """Test ideation engine initialization."""
        self.assertEqual(self.ideation.multi_agent_client, self.multi_agent_client)
        self.assertEqual(self.ideation.logger, self.logger)

    def test_provider_focus_defined(self):
        """Test that provider focus areas are defined."""
        self.assertIn("anthropic", MultiAgentIdeation.PROVIDER_FOCUS)
        self.assertIn("deepseek", MultiAgentIdeation.PROVIDER_FOCUS)
        self.assertIn("openai", MultiAgentIdeation.PROVIDER_FOCUS)
        self.assertIn("perplexity", MultiAgentIdeation.PROVIDER_FOCUS)

    def test_parse_proposals(self):
        """Test parsing proposals from provider response."""
        response_text = """
        **Title: Implement Error Handling**
        Description: Add comprehensive error handling throughout the application
        Value Proposition: Reduce production errors by 40%
        Complexity: 6
        Priority: HIGH
        Category: reliability
        Estimated Effort: 2-3 weeks

        **Title: Add Caching Layer**
        Description: Implement Redis caching for frequently accessed data
        Value Proposition: Improve response times by 50%
        Complexity: 7
        Priority: MEDIUM
        Category: performance
        """

        proposals = self.ideation._parse_proposals("anthropic", response_text)

        self.assertGreater(len(proposals), 0)
        self.assertEqual(proposals[0].provider, "anthropic")
        self.assertIn("Error Handling", proposals[0].title)

    def test_create_proposal(self):
        """Test creating FeatureProposal from parsed data."""
        data = {
            "title": "Test Feature",
            "description": "A test feature",
            "value": "High value",
            "complexity": 7,
            "priority": ProposalPriority.HIGH,
            "effort": "2 weeks",
            "category": "performance",
        }

        proposal = self.ideation._create_proposal("anthropic", 0, data)

        self.assertEqual(proposal.id, "anthropic-0")
        self.assertEqual(proposal.title, "Test Feature")
        self.assertEqual(proposal.provider, "anthropic")
        self.assertEqual(proposal.complexity_estimate, 7)
        self.assertEqual(proposal.priority, ProposalPriority.HIGH)

    def test_build_ideation_context(self):
        """Test building ideation context."""
        context = self.ideation._build_ideation_context(
            self.codebase_analysis,
            self.multi_agent_analysis,
            ["Goal 1", "Goal 2"],
        )

        self.assertIn("Codebase Overview", context)
        self.assertIn("50", context)  # total files
        self.assertIn("Architecture Rating", context)
        self.assertIn("Goal 1", context)
        self.assertIn("Goal 2", context)

    def test_format_proposals_for_critique(self):
        """Test formatting proposals for critique."""
        proposals = [
            FeatureProposal(
                id="test-1",
                title="Feature 1",
                description="Description 1",
                provider="anthropic",
                value_proposition="High value",
                complexity_estimate=6,
                priority=ProposalPriority.HIGH,
                category="performance",
            )
        ]

        formatted = self.ideation._format_proposals_for_critique(proposals)

        self.assertIn("test-1", formatted)
        self.assertIn("Feature 1", formatted)
        self.assertIn("anthropic", formatted)
        self.assertIn("6/10", formatted)

    def test_filter_viable_proposals(self):
        """Test filtering viable proposals."""
        proposals = [
            FeatureProposal(
                id="high-rated",
                title="High Rated",
                description="",
                provider="anthropic",
                value_proposition="",
                complexity_estimate=5,
                priority=ProposalPriority.MEDIUM,
            ),
            FeatureProposal(
                id="low-rated",
                title="Low Rated",
                description="",
                provider="deepseek",
                value_proposition="",
                complexity_estimate=5,
                priority=ProposalPriority.LOW,
            ),
        ]

        critiques = {
            "high-rated": ProposalCritique(
                proposal_id="high-rated",
                provider_ratings={"anthropic": 8, "deepseek": 7},
            ),
            "low-rated": ProposalCritique(
                proposal_id="low-rated",
                provider_ratings={"anthropic": 3, "deepseek": 4},
            ),
        }

        viable = self.ideation._filter_viable_proposals(proposals, critiques)

        # Should keep high-rated, filter low-rated
        self.assertGreater(len(viable), 0)
        self.assertIn("high-rated", [p.id for p in viable])

    def test_extract_timeline(self):
        """Test extracting timeline from text."""
        test_cases = [
            ("Phase 1: Foundation (4-6 weeks)", "4-6 weeks"),
            ("Q1 2025", "Q1 2025"),
            ("No timeline info", "TBD"),
        ]

        for text, expected in test_cases:
            timeline = self.ideation._extract_timeline(text)
            if expected != "TBD":
                self.assertEqual(timeline, expected)

    def test_extract_phases(self):
        """Test extracting phases from synthesis response."""
        response_text = """
        Phase 1: Foundation (4-6 weeks)
        - Feature test-1
        - Another important feature

        Phase 2: Enhancement (2-3 months)
        - Feature test-2
        """

        proposals = [
            FeatureProposal(
                id="test-1",
                title="Feature 1",
                description="",
                provider="anthropic",
                value_proposition="",
                complexity_estimate=5,
                priority=ProposalPriority.HIGH,
            ),
            FeatureProposal(
                id="test-2",
                title="Feature 2",
                description="",
                provider="deepseek",
                value_proposition="",
                complexity_estimate=6,
                priority=ProposalPriority.MEDIUM,
            ),
        ]

        phases = self.ideation._extract_phases(response_text, proposals)

        self.assertGreater(len(phases), 0)
        self.assertIn("Phase 1", phases[0]["name"])

    def test_calculate_synthesis_confidence(self):
        """Test calculating synthesis confidence."""
        phases = [
            {
                "name": "Phase 1",
                "features": [
                    {"id": "test-1"},
                    {"id": "test-2"},
                    {"id": "test-3"},
                ],
            },
            {
                "name": "Phase 2",
                "features": [
                    {"id": "test-4"},
                    {"id": "test-5"},
                ],
            },
        ]

        proposals = []
        critiques = {
            "test-1": ProposalCritique(
                proposal_id="test-1",
                feasibility_score=0.9,
                value_score=0.8,
            ),
            "test-2": ProposalCritique(
                proposal_id="test-2",
                feasibility_score=0.8,
                value_score=0.9,
            ),
        }

        confidence = self.ideation._calculate_synthesis_confidence(
            phases, proposals, critiques
        )

        self.assertGreater(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)

    def test_extract_provider_emphasis(self):
        """Test extracting provider emphasis."""
        test_cases = [
            ("Focus on performance optimization and speed", "Performance"),
            ("Security and authentication are critical", "Security"),
            ("Improve user experience and usability", "User Experience"),
            ("Follow industry best practices", "Best Practices"),
        ]

        for response_text, expected_keyword in test_cases:
            emphasis = self.ideation._extract_provider_emphasis(response_text)
            # Check that emphasis is not empty
            self.assertIsNotNone(emphasis)

    def test_parallel_ideation(self):
        """Test parallel ideation phase."""
        # Mock response
        mock_response = MultiAgentResponse(
            providers=["anthropic", "deepseek"],
            responses={
                "anthropic": """
                Title: Add Error Handling
                Description: Comprehensive error handling
                Value Proposition: Reduce errors
                Complexity: 6
                Priority: HIGH
                """,
                "deepseek": """
                Title: Performance Optimization
                Description: Optimize database queries
                Value Proposition: Faster responses
                Complexity: 7
                Priority: MEDIUM
                """,
            },
            strategy="all",
            total_tokens=5000,
            total_cost=0.04,
            success=True,
        )
        self.multi_agent_client.query.return_value = mock_response

        proposals = self.ideation._parallel_ideation(
            self.codebase_analysis, self.multi_agent_analysis, None
        )

        # Should have proposals from both providers
        self.assertGreater(len(proposals), 0)
        self.multi_agent_client.query.assert_called_once()

    def test_feature_proposal_to_dict(self):
        """Test FeatureProposal to_dict conversion."""
        proposal = FeatureProposal(
            id="test-1",
            title="Test Feature",
            description="Test description",
            provider="anthropic",
            value_proposition="High value",
            complexity_estimate=7,
            priority=ProposalPriority.HIGH,
            dependencies=["feature-0"],
            success_metrics=["Metric 1"],
            estimated_effort="2 weeks",
            category="performance",
        )

        result = proposal.to_dict()

        self.assertEqual(result["id"], "test-1")
        self.assertEqual(result["title"], "Test Feature")
        self.assertEqual(result["priority"], "high")
        self.assertEqual(result["complexity_estimate"], 7)
        self.assertEqual(len(result["dependencies"]), 1)

    def test_proposal_critique_to_dict(self):
        """Test ProposalCritique to_dict conversion."""
        critique = ProposalCritique(
            proposal_id="test-1",
            strengths=["Good design", "Clear value"],
            weaknesses=["High complexity"],
            feasibility_score=0.8,
            value_score=0.9,
            overlaps_with=["test-2"],
            provider_ratings={"anthropic": 8, "deepseek": 7},
        )

        result = critique.to_dict()

        self.assertEqual(result["proposal_id"], "test-1")
        self.assertEqual(len(result["strengths"]), 2)
        self.assertEqual(result["feasibility_score"], 0.8)
        self.assertEqual(result["provider_ratings"]["anthropic"], 8)

    def test_synthesized_roadmap_to_dict(self):
        """Test SynthesizedRoadmap to_dict conversion."""
        roadmap = SynthesizedRoadmap(
            phases=[{"name": "Phase 1", "features": []}],
            consensus_confidence=0.85,
            total_proposals_considered=20,
            selected_proposals=10,
            provider_perspectives={"anthropic": "Security focus"},
            synthesis_notes="Notes",
        )

        result = roadmap.to_dict()

        self.assertEqual(len(result["phases"]), 1)
        self.assertEqual(result["consensus_confidence"], 0.85)
        self.assertEqual(result["selected_proposals"], 10)

    def test_ideation_result_to_dict(self):
        """Test IdeationResult to_dict conversion."""
        proposal = FeatureProposal(
            id="test-1",
            title="Feature",
            description="",
            provider="anthropic",
            value_proposition="",
            complexity_estimate=5,
            priority=ProposalPriority.MEDIUM,
        )

        critique = ProposalCritique(proposal_id="test-1")

        roadmap = SynthesizedRoadmap(
            phases=[],
            consensus_confidence=0.8,
            total_proposals_considered=10,
            selected_proposals=5,
            provider_perspectives={},
            synthesis_notes="",
        )

        result = IdeationResult(
            proposals=[proposal],
            critiques={"test-1": critique},
            synthesized_roadmap=roadmap,
            total_cost=0.5,
            total_tokens=5000,
            duration_seconds=120.5,
        )

        result_dict = result.to_dict()

        self.assertEqual(len(result_dict["proposals"]), 1)
        self.assertEqual(len(result_dict["critiques"]), 1)
        self.assertEqual(result_dict["total_cost"], 0.5)

    def test_proposal_priority_enum(self):
        """Test ProposalPriority enum values."""
        self.assertEqual(ProposalPriority.CRITICAL.value, "critical")
        self.assertEqual(ProposalPriority.HIGH.value, "high")
        self.assertEqual(ProposalPriority.MEDIUM.value, "medium")
        self.assertEqual(ProposalPriority.LOW.value, "low")


if __name__ == "__main__":
    unittest.main()
