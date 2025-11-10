"""Unit tests for MultiAgentAnalyzer."""

import unittest
from unittest.mock import Mock
from datetime import datetime, timezone

from src.analyzers.multi_agent_analyzer import (
    MultiAgentAnalyzer,
    ProviderInsight,
    ConsensusInsights,
    MultiAgentAnalysisResult,
)
from src.analyzers.codebase_analyzer import (
    CodebaseAnalysis,
    CodebaseMetrics,
    DependencyInfo,
)
from src.integrations.multi_agent_coder_client import (
    MultiAgentCoderClient,
    MultiAgentResponse,
    MultiAgentStrategy,
)
from src.core.logger import AuditLogger


class TestMultiAgentAnalyzer(unittest.TestCase):
    """Test cases for MultiAgentAnalyzer."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.multi_agent_client = Mock(spec=MultiAgentCoderClient)

        self.analyzer = MultiAgentAnalyzer(
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

    def test_initialization(self):
        """Test analyzer initialization."""
        self.assertEqual(self.analyzer.multi_agent_client, self.multi_agent_client)
        self.assertEqual(self.analyzer.logger, self.logger)

    def test_provider_focus_defined(self):
        """Test that provider focus areas are defined."""
        self.assertIn("anthropic", MultiAgentAnalyzer.PROVIDER_FOCUS)
        self.assertIn("deepseek", MultiAgentAnalyzer.PROVIDER_FOCUS)
        self.assertIn("openai", MultiAgentAnalyzer.PROVIDER_FOCUS)
        self.assertIn("perplexity", MultiAgentAnalyzer.PROVIDER_FOCUS)

    def test_analyze_architecture(self):
        """Test architecture analysis."""
        # Mock response
        mock_response = MultiAgentResponse(
            providers=["anthropic", "deepseek"],
            responses={
                "anthropic": "Architecture Quality: 8/10. Patterns: MVC, Repository",
                "deepseek": "Rating 7/10. Uses Singleton pattern",
            },
            strategy="all",
            total_tokens=5000,
            total_cost=0.04,
            success=True,
        )
        self.multi_agent_client.query.return_value = mock_response

        response = self.analyzer._analyze_architecture(self.codebase_analysis)

        # Verify query was called with correct strategy
        self.multi_agent_client.query.assert_called_once()
        call_args = self.multi_agent_client.query.call_args
        self.assertEqual(call_args[1]["strategy"], MultiAgentStrategy.ALL)
        self.assertIn("architecture", call_args[1]["prompt"].lower())

    def test_analyze_technical_debt(self):
        """Test technical debt analysis."""
        mock_response = MultiAgentResponse(
            providers=["anthropic", "deepseek"],
            responses={
                "anthropic": "High priority: refactor auth. Code quality issues: duplicate code",
                "deepseek": "Technical debt: complex dependencies, outdated libraries",
            },
            strategy="dialectical",
            total_tokens=6000,
            total_cost=0.05,
            success=True,
        )
        self.multi_agent_client.query.return_value = mock_response

        response = self.analyzer._analyze_technical_debt(self.codebase_analysis)

        # Verify query was called with dialectical strategy
        self.multi_agent_client.query.assert_called_once()
        call_args = self.multi_agent_client.query.call_args
        self.assertEqual(call_args[1]["strategy"], MultiAgentStrategy.DIALECTICAL)
        self.assertIn("debt", call_args[1]["prompt"].lower())

    def test_identify_gaps(self):
        """Test gap identification."""
        mock_response = MultiAgentResponse(
            providers=["anthropic", "openai"],
            responses={
                "anthropic": "Missing: error handling, logging. Need to implement retry logic",
                "openai": "Should add rate limiting, need better documentation",
            },
            strategy="all",
            total_tokens=4500,
            total_cost=0.035,
            success=True,
        )
        self.multi_agent_client.query.return_value = mock_response

        response = self.analyzer._identify_gaps(self.codebase_analysis)

        # Verify query was called
        self.multi_agent_client.query.assert_called_once()
        call_args = self.multi_agent_client.query.call_args
        self.assertEqual(call_args[1]["strategy"], MultiAgentStrategy.ALL)
        self.assertIn("gap", call_args[1]["prompt"].lower())

    def test_parse_provider_response_architecture_rating(self):
        """Test parsing architecture rating from response."""
        insight = self.analyzer._parse_provider_response(
            provider="anthropic",
            arch_response="Architecture Quality: Rate 8/10. Well organized.",
            debt_response="",
            gap_response="",
        )

        self.assertEqual(insight.provider, "anthropic")
        self.assertEqual(insight.architecture_rating, 8)

    def test_parse_provider_response_patterns(self):
        """Test parsing architectural patterns from response."""
        insight = self.analyzer._parse_provider_response(
            provider="deepseek",
            arch_response="Uses MVC pattern with Singleton and Factory patterns",
            debt_response="",
            gap_response="",
        )

        self.assertIn("MVC", insight.architecture_patterns)
        self.assertIn("Singleton", insight.architecture_patterns)
        self.assertIn("Factory", insight.architecture_patterns)

    def test_parse_provider_response_recommendations(self):
        """Test parsing recommendations from response."""
        insight = self.analyzer._parse_provider_response(
            provider="openai",
            arch_response="Recommend: Implement caching. Suggest: Add monitoring.",
            debt_response="",
            gap_response="",
        )

        self.assertGreater(len(insight.recommendations), 0)

    def test_parse_provider_response_technical_debt(self):
        """Test parsing technical debt areas."""
        insight = self.analyzer._parse_provider_response(
            provider="anthropic",
            arch_response="",
            debt_response="Need to refactor auth. Code has duplicate logic. Complex dependencies.",
            gap_response="",
        )

        self.assertIn("Refactor", insight.technical_debt_areas)
        self.assertIn("Duplicate", insight.technical_debt_areas)
        self.assertIn("Complex", insight.technical_debt_areas)

    def test_parse_provider_response_improvements(self):
        """Test parsing improvement opportunities."""
        insight = self.analyzer._parse_provider_response(
            provider="perplexity",
            arch_response="",
            debt_response="",
            gap_response="""
            - Missing error handling in auth module
            - Need to add logging throughout
            - Should implement retry logic
            - Missing integration tests
            """,
        )

        self.assertGreater(len(insight.improvement_opportunities), 0)
        # Should extract lines with keywords
        opportunities = " ".join(insight.improvement_opportunities).lower()
        self.assertTrue(
            any(
                keyword in opportunities
                for keyword in ["missing", "need", "should", "implement"]
            )
        )

    def test_build_provider_insights(self):
        """Test building provider insights from responses."""
        arch_response = MultiAgentResponse(
            providers=["anthropic", "deepseek"],
            responses={
                "anthropic": "Rating 8/10. Uses MVC pattern.",
                "deepseek": "Score: 7/10. Singleton pattern observed.",
            },
            strategy="all",
            total_tokens=5000,
            total_cost=0.04,
            success=True,
        )

        debt_response = MultiAgentResponse(
            providers=["anthropic", "deepseek"],
            responses={
                "anthropic": "Need to refactor authentication.",
                "deepseek": "Complex dependencies detected.",
            },
            strategy="dialectical",
            total_tokens=6000,
            total_cost=0.05,
            success=True,
        )

        gap_response = MultiAgentResponse(
            providers=["anthropic", "deepseek"],
            responses={
                "anthropic": "Missing error handling.",
                "deepseek": "Need to add logging.",
            },
            strategy="all",
            total_tokens=4000,
            total_cost=0.03,
            success=True,
        )

        insights = self.analyzer._build_provider_insights(
            arch_response, debt_response, gap_response
        )

        # Should have insights for both providers
        self.assertIn("anthropic", insights)
        self.assertIn("deepseek", insights)

        # Verify structure
        anthropic_insight = insights["anthropic"]
        self.assertIsInstance(anthropic_insight, ProviderInsight)
        self.assertEqual(anthropic_insight.provider, "anthropic")

    def test_build_consensus_ratings(self):
        """Test building consensus from ratings."""
        provider_insights = {
            "anthropic": ProviderInsight(
                provider="anthropic",
                architecture_rating=8,
                code_quality_rating=7,
            ),
            "deepseek": ProviderInsight(
                provider="deepseek",
                architecture_rating=7,
                code_quality_rating=8,
            ),
            "openai": ProviderInsight(
                provider="openai",
                architecture_rating=9,
                code_quality_rating=8,
            ),
        }

        consensus = self.analyzer._build_consensus(provider_insights)

        # Should average ratings
        self.assertAlmostEqual(consensus.overall_architecture_rating, 8.0, places=1)
        self.assertAlmostEqual(consensus.overall_quality_rating, 7.67, places=1)

    def test_build_consensus_patterns(self):
        """Test consensus pattern detection."""
        provider_insights = {
            "anthropic": ProviderInsight(
                provider="anthropic",
                architecture_patterns=["MVC", "Repository"],
            ),
            "deepseek": ProviderInsight(
                provider="deepseek",
                architecture_patterns=["MVC", "Singleton"],
            ),
            "openai": ProviderInsight(
                provider="openai",
                architecture_patterns=["MVC", "Factory"],
            ),
        }

        consensus = self.analyzer._build_consensus(provider_insights)

        # MVC mentioned by all providers
        self.assertIn("MVC", consensus.consensus_patterns)
        # Others mentioned by only 1 provider each
        self.assertNotIn("Repository", consensus.consensus_patterns)

    def test_build_consensus_priorities(self):
        """Test consensus priority building."""
        provider_insights = {
            "anthropic": ProviderInsight(
                provider="anthropic",
                improvement_opportunities=["Add error handling", "Improve logging"],
                technical_debt_areas=["Refactor", "Complex"],
            ),
            "deepseek": ProviderInsight(
                provider="deepseek",
                improvement_opportunities=["Add error handling", "Add tests"],
                technical_debt_areas=["Refactor", "Outdated"],
            ),
        }

        consensus = self.analyzer._build_consensus(provider_insights)

        # Should have top priorities
        self.assertGreater(len(consensus.top_priorities), 0)

        # "Add error handling" mentioned by both providers
        error_handling_priority = next(
            (
                p
                for p in consensus.top_priorities
                if "error handling" in p["description"].lower()
            ),
            None,
        )
        self.assertIsNotNone(error_handling_priority)
        self.assertEqual(
            error_handling_priority["confidence"], 1.0
        )  # Both mentioned it

        # "Refactor" mentioned by both
        refactor_priority = next(
            (
                p
                for p in consensus.top_priorities
                if "refactor" in p["description"].lower()
            ),
            None,
        )
        self.assertIsNotNone(refactor_priority)

    def test_build_consensus_confidence(self):
        """Test consensus confidence calculation."""
        provider_insights = {
            "anthropic": ProviderInsight(
                provider="anthropic",
                architecture_rating=8,
                improvement_opportunities=["Fix auth", "Add logging"],
            ),
            "deepseek": ProviderInsight(
                provider="deepseek",
                architecture_rating=7,
                improvement_opportunities=["Fix auth", "Add tests"],
            ),
        }

        consensus = self.analyzer._build_consensus(provider_insights)

        # Should have confidence score
        self.assertGreater(consensus.consensus_confidence, 0.0)
        self.assertLessEqual(consensus.consensus_confidence, 1.0)

    def test_build_consensus_empty(self):
        """Test consensus building with empty insights."""
        consensus = self.analyzer._build_consensus({})

        self.assertEqual(consensus.overall_architecture_rating, 0.0)
        self.assertEqual(consensus.overall_quality_rating, 0.0)
        self.assertEqual(len(consensus.consensus_patterns), 0)
        self.assertEqual(len(consensus.top_priorities), 0)
        self.assertEqual(consensus.consensus_confidence, 0.0)

    def test_format_patterns(self):
        """Test pattern formatting."""
        patterns = {
            "has_tests": True,
            "test_files_count": 15,
            "has_documentation": True,
            "documentation_files": ["README.md", "CONTRIBUTING.md"],
            "frameworks": {"flask": True, "react": True},
            "architecture_pattern": "MVC-like",
        }

        formatted = self.analyzer._format_patterns(patterns)

        self.assertIn("Tests:", formatted)
        self.assertIn("15 test files", formatted)
        self.assertIn("Documentation:", formatted)
        self.assertIn("2 docs", formatted)
        self.assertIn("Frameworks:", formatted)
        self.assertIn("flask", formatted)
        self.assertIn("Architecture:", formatted)
        self.assertIn("MVC-like", formatted)

    def test_format_patterns_no_tests(self):
        """Test formatting patterns without tests."""
        patterns = {"has_tests": False}

        formatted = self.analyzer._format_patterns(patterns)

        # Should not include test info if no tests
        self.assertNotIn("Tests:", formatted)

    def test_analyze_with_multi_agent_complete(self):
        """Test complete multi-agent analysis."""
        # Mock all three analysis calls
        arch_response = MultiAgentResponse(
            providers=["anthropic", "deepseek"],
            responses={
                "anthropic": "Architecture Rating: 8/10. Uses MVC pattern. Recommend: Add caching",
                "deepseek": "Score: 7/10. Singleton pattern. Performance could improve.",
            },
            strategy="all",
            total_tokens=5000,
            total_cost=0.04,
            success=True,
        )

        debt_response = MultiAgentResponse(
            providers=["anthropic", "deepseek"],
            responses={
                "anthropic": "High priority: refactor auth. Complex code detected.",
                "deepseek": "Technical debt: duplicate logic, outdated dependencies.",
            },
            strategy="dialectical",
            total_tokens=6000,
            total_cost=0.05,
            success=True,
        )

        gap_response = MultiAgentResponse(
            providers=["anthropic", "deepseek"],
            responses={
                "anthropic": "Missing: error handling. Need to implement logging.",
                "deepseek": "Should add rate limiting. Missing integration tests.",
            },
            strategy="all",
            total_tokens=4000,
            total_cost=0.03,
            success=True,
        )

        self.multi_agent_client.query.side_effect = [
            arch_response,
            debt_response,
            gap_response,
        ]

        # Perform analysis
        result = self.analyzer.analyze_with_multi_agent(
            self.codebase_analysis, "test-analysis-123"
        )

        # Verify result structure
        self.assertIsInstance(result, MultiAgentAnalysisResult)
        self.assertEqual(result.analysis_id, "test-analysis-123")

        # Verify provider insights
        self.assertIn("anthropic", result.provider_insights)
        self.assertIn("deepseek", result.provider_insights)

        # Verify consensus
        self.assertIsInstance(result.consensus, ConsensusInsights)
        self.assertGreater(result.consensus.overall_architecture_rating, 0)
        self.assertGreater(result.consensus.consensus_confidence, 0)

        # Verify raw codebase analysis included
        self.assertEqual(result.raw_codebase_analysis, self.codebase_analysis)

        # Verify query was called 3 times
        self.assertEqual(self.multi_agent_client.query.call_count, 3)

    def test_provider_insight_to_dict(self):
        """Test ProviderInsight to_dict conversion."""
        insight = ProviderInsight(
            provider="anthropic",
            architecture_rating=8,
            architecture_patterns=["MVC", "Repository"],
            code_quality_rating=7,
            technical_debt_areas=["Refactor", "Complex"],
            improvement_opportunities=["Add error handling"],
            security_concerns=["SQL injection risk"],
            performance_issues=["N+1 queries"],
            recommendations=["Use connection pooling"],
        )

        result = insight.to_dict()

        self.assertEqual(result["provider"], "anthropic")
        self.assertEqual(result["architecture_rating"], 8)
        self.assertEqual(len(result["architecture_patterns"]), 2)
        self.assertEqual(len(result["technical_debt_areas"]), 2)

    def test_consensus_insights_to_dict(self):
        """Test ConsensusInsights to_dict conversion."""
        consensus = ConsensusInsights(
            overall_architecture_rating=8.0,
            overall_quality_rating=7.5,
            consensus_patterns=["MVC", "Repository"],
            top_priorities=[
                {
                    "priority": "high",
                    "category": "improvement",
                    "description": "Add error handling",
                    "confidence": 0.9,
                }
            ],
            consensus_confidence=0.85,
            divergent_opinions=[{"topic": "testing", "split": "2-1"}],
        )

        result = consensus.to_dict()

        self.assertEqual(result["overall_architecture_rating"], 8.0)
        self.assertEqual(len(result["consensus_patterns"]), 2)
        self.assertEqual(len(result["top_priorities"]), 1)
        self.assertEqual(result["consensus_confidence"], 0.85)

    def test_multi_agent_analysis_result_to_dict(self):
        """Test MultiAgentAnalysisResult to_dict conversion."""
        # Mock responses for the three queries
        self.multi_agent_client.query.side_effect = [
            MultiAgentResponse(
                providers=["anthropic"],
                responses={"anthropic": "Rating: 8/10"},
                strategy="all",
                total_tokens=1000,
                total_cost=0.01,
                success=True,
            ),
            MultiAgentResponse(
                providers=["anthropic"],
                responses={"anthropic": "Debt: refactor needed"},
                strategy="dialectical",
                total_tokens=1000,
                total_cost=0.01,
                success=True,
            ),
            MultiAgentResponse(
                providers=["anthropic"],
                responses={"anthropic": "Missing: tests"},
                strategy="all",
                total_tokens=1000,
                total_cost=0.01,
                success=True,
            ),
        ]

        result = self.analyzer.analyze_with_multi_agent(
            self.codebase_analysis, "test-123"
        )
        result_dict = result.to_dict()

        self.assertIn("analysis_id", result_dict)
        self.assertIn("analyzed_at", result_dict)
        self.assertIn("provider_insights", result_dict)
        self.assertIn("consensus", result_dict)
        self.assertIn("raw_codebase_analysis", result_dict)


if __name__ == "__main__":
    unittest.main()
