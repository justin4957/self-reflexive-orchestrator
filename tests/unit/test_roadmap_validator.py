"""Unit tests for RoadmapValidator."""

import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from src.core.logger import AuditLogger
from src.cycles.multi_agent_ideation import (FeatureProposal, IdeationResult,
                                             ProposalPriority,
                                             SynthesizedRoadmap)
from src.cycles.roadmap_validator import (DialecticalValidation,
                                          ProposalValidation, RoadmapValidator,
                                          ValidatedRoadmap,
                                          ValidationCriterion,
                                          ValidationDecision)
from src.integrations.multi_agent_coder_client import (MultiAgentCoderClient,
                                                       MultiAgentResponse,
                                                       MultiAgentStrategy)


class TestRoadmapValidator(unittest.TestCase):
    """Test cases for RoadmapValidator."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.multi_agent_client = Mock(spec=MultiAgentCoderClient)

        self.validator = RoadmapValidator(
            multi_agent_client=self.multi_agent_client,
            logger=self.logger,
            min_confidence=0.8,
        )

        # Create sample proposals
        self.proposals = [
            FeatureProposal(
                id="test-1",
                title="Add Error Handling",
                description="Comprehensive error handling",
                provider="anthropic",
                value_proposition="Reduce errors",
                complexity_estimate=6,
                priority=ProposalPriority.HIGH,
            ),
            FeatureProposal(
                id="test-2",
                title="Performance Optimization",
                description="Optimize queries",
                provider="deepseek",
                value_proposition="Faster responses",
                complexity_estimate=7,
                priority=ProposalPriority.MEDIUM,
            ),
        ]

        # Create sample roadmap
        self.roadmap = SynthesizedRoadmap(
            phases=[
                {
                    "name": "Phase 1",
                    "features": [
                        {"id": "test-1", "title": "Add Error Handling"},
                        {"id": "test-2", "title": "Performance Optimization"},
                    ],
                }
            ],
            consensus_confidence=0.85,
            total_proposals_considered=10,
            selected_proposals=2,
            provider_perspectives={},
            synthesis_notes="",
        )

        # Create sample ideation result
        self.ideation_result = IdeationResult(
            proposals=self.proposals,
            critiques={},
            synthesized_roadmap=self.roadmap,
            total_cost=0.5,
            total_tokens=5000,
            duration_seconds=120.0,
        )

    def test_initialization(self):
        """Test validator initialization."""
        self.assertEqual(self.validator.multi_agent_client, self.multi_agent_client)
        self.assertEqual(self.validator.logger, self.logger)
        self.assertEqual(self.validator.min_confidence, 0.8)

    def test_validation_criteria_keywords(self):
        """Test that validation criteria keywords are defined."""
        self.assertIn(ValidationCriterion.ALIGNMENT, RoadmapValidator.CRITERIA_KEYWORDS)
        self.assertIn(
            ValidationCriterion.FEASIBILITY, RoadmapValidator.CRITERIA_KEYWORDS
        )
        self.assertIn(ValidationCriterion.PRIORITY, RoadmapValidator.CRITERIA_KEYWORDS)
        self.assertIn(ValidationCriterion.SCOPE, RoadmapValidator.CRITERIA_KEYWORDS)
        self.assertIn(
            ValidationCriterion.DEPENDENCIES, RoadmapValidator.CRITERIA_KEYWORDS
        )
        self.assertIn(ValidationCriterion.VALUE, RoadmapValidator.CRITERIA_KEYWORDS)

    def test_format_proposals_for_validation(self):
        """Test formatting proposals for validation."""
        formatted = self.validator._format_proposals_for_validation(self.proposals)

        self.assertIn("test-1", formatted)
        self.assertIn("Add Error Handling", formatted)
        self.assertIn("ANTHROPIC", formatted)
        self.assertIn("6/10", formatted)
        self.assertIn("Comprehensive error handling", formatted)

    def test_extract_decision_approved(self):
        """Test extracting approved decision."""
        text = "This proposal is approved and ready to implement."
        decision = self.validator._extract_decision(text)
        self.assertEqual(decision, ValidationDecision.APPROVED)

    def test_extract_decision_approved_with_changes(self):
        """Test extracting approved with changes decision."""
        text = "Approved with changes - needs minor adjustments."
        decision = self.validator._extract_decision(text)
        self.assertEqual(decision, ValidationDecision.APPROVED_WITH_CHANGES)

    def test_extract_decision_needs_revision(self):
        """Test extracting needs revision decision."""
        text = "This needs revision before we can proceed."
        decision = self.validator._extract_decision(text)
        self.assertEqual(decision, ValidationDecision.NEEDS_REVISION)

    def test_extract_decision_rejected(self):
        """Test extracting rejected decision."""
        text = "This proposal should be rejected due to high risk."
        decision = self.validator._extract_decision(text)
        self.assertEqual(decision, ValidationDecision.REJECTED)

    def test_extract_confidence(self):
        """Test extracting confidence score."""
        test_cases = [
            ("Confidence: 0.85", 0.85),
            ("confidence: 0.9", 0.9),
            ("Confidence: 7.5", 0.75),  # Out of 10
            ("No explicit score", 0.75),  # Default
        ]

        for text, expected in test_cases:
            confidence = self.validator._extract_confidence(text)
            self.assertAlmostEqual(confidence, expected, places=2)

    def test_extract_criteria_scores(self):
        """Test extracting criteria scores."""
        text = """
        Alignment: 0.9
        Feasibility: 0.85
        Priority: 0.8
        Scope: 0.7
        Dependencies: 0.95
        Value: 0.88
        """

        scores = self.validator._extract_criteria_scores(text)

        # Should extract at least some scores
        self.assertGreater(len(scores), 0)
        # Check that at least one of the criteria was extracted
        self.assertTrue(
            any(
                criterion in scores
                for criterion in [
                    ValidationCriterion.PRIORITY,
                    ValidationCriterion.SCOPE,
                    ValidationCriterion.VALUE,
                ]
            )
        )

    def test_extract_list_items(self):
        """Test extracting list items."""
        text = """
        Strengths:
        - Well designed architecture
        - Clear value proposition
        - Good test coverage

        Concerns:
        - High complexity
        - Timeline risk
        """

        strengths = self.validator._extract_list_items(text, "strength")
        concerns = self.validator._extract_list_items(text, "concern")

        self.assertGreater(len(strengths), 0)
        self.assertGreater(len(concerns), 0)

    def test_extract_combined_response(self):
        """Test extracting combined response text."""
        response = MultiAgentResponse(
            providers=["anthropic", "deepseek"],
            responses={
                "anthropic": "Anthropic analysis here",
                "deepseek": "DeepSeek analysis here",
            },
            strategy="all",
            total_tokens=1000,
            total_cost=0.01,
            success=True,
        )

        combined = self.validator._extract_combined_response(response)

        self.assertIn("ANTHROPIC", combined)
        self.assertIn("DEEPSEEK", combined)
        self.assertIn("Anthropic analysis here", combined)
        self.assertIn("DeepSeek analysis here", combined)

    def test_calculate_consensus_confidence(self):
        """Test calculating consensus confidence."""
        response = MultiAgentResponse(
            providers=["anthropic"],
            responses={
                "anthropic": """
                Confidence: 0.85
                Overall assessment confidence: 0.9
                """
            },
            strategy="dialectical",
            total_tokens=1000,
            total_cost=0.01,
            success=True,
        )

        confidence = self.validator._calculate_consensus_confidence(response)

        self.assertGreater(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)

    def test_parse_proposal_validation_approved(self):
        """Test parsing proposal validation - approved."""
        synthesis_text = """
        Proposal: test-1
        Decision: APPROVED
        Confidence: 0.9
        Rationale: Strong value proposition and feasibility
        Strengths:
        - Well scoped
        - Clear benefits
        """

        validation = self.validator._parse_proposal_validation(
            self.proposals[0], synthesis_text
        )

        self.assertEqual(validation.proposal_id, "test-1")
        self.assertEqual(validation.decision, ValidationDecision.APPROVED)
        self.assertAlmostEqual(validation.confidence, 0.9, places=1)
        self.assertGreater(len(validation.strengths), 0)

    def test_parse_proposal_validation_rejected(self):
        """Test parsing proposal validation - rejected."""
        synthesis_text = """
        Proposal: test-2
        Decision: REJECTED
        Confidence: 0.85
        Rationale: Too risky and high complexity
        Concerns:
        - Technical debt
        - Timeline risk
        """

        validation = self.validator._parse_proposal_validation(
            self.proposals[1], synthesis_text
        )

        self.assertEqual(validation.proposal_id, "test-2")
        self.assertEqual(validation.decision, ValidationDecision.REJECTED)
        self.assertGreater(len(validation.concerns), 0)

    def test_generate_refined_phases(self):
        """Test generating refined phases with approved proposals."""
        approved = [self.proposals[0]]  # Only test-1 approved

        refined = self.validator._generate_refined_phases(approved, self.roadmap.phases)

        self.assertEqual(len(refined), 1)
        self.assertEqual(len(refined[0]["features"]), 1)
        self.assertEqual(refined[0]["features"][0]["id"], "test-1")

    def test_calculate_overall_confidence(self):
        """Test calculating overall confidence."""
        validated_proposals = {
            "test-1": ProposalValidation(
                proposal_id="test-1",
                decision=ValidationDecision.APPROVED,
                confidence=0.9,
            ),
            "test-2": ProposalValidation(
                proposal_id="test-2",
                decision=ValidationDecision.APPROVED,
                confidence=0.85,
            ),
        }

        dialectical_confidence = 0.88

        overall = self.validator._calculate_overall_confidence(
            validated_proposals, dialectical_confidence
        )

        self.assertGreater(overall, 0.0)
        self.assertLessEqual(overall, 1.0)
        # Should be weighted average: 0.6 * 0.88 + 0.4 * 0.875
        expected = 0.6 * 0.88 + 0.4 * 0.875
        self.assertAlmostEqual(overall, expected, places=2)

    def test_validate_roadmap_integration(self):
        """Test complete validation workflow."""
        # Mock responses for three phases
        thesis_response = MultiAgentResponse(
            providers=["anthropic", "deepseek"],
            responses={
                "anthropic": """
                Proposal test-1: APPROVED
                Strong alignment with goals
                Confidence: 0.9
                """,
                "deepseek": """
                Proposal test-2: APPROVED
                Good performance benefits
                Confidence: 0.85
                """,
            },
            strategy="all",
            total_tokens=2000,
            total_cost=0.02,
            success=True,
        )

        antithesis_response = MultiAgentResponse(
            providers=["anthropic"],
            responses={
                "anthropic": """
                Concerns for test-1:
                - Implementation complexity
                Risks:
                - Timeline risk
                """
            },
            strategy="dialectical",
            total_tokens=1500,
            total_cost=0.015,
            success=True,
        )

        synthesis_response = MultiAgentResponse(
            providers=["anthropic"],
            responses={
                "anthropic": """
                Proposal: test-1
                Decision: APPROVED
                Confidence: 0.88
                Rationale: Benefits outweigh concerns

                Proposal: test-2
                Decision: APPROVED_WITH_CHANGES
                Confidence: 0.82
                Suggestions:
                - Add performance benchmarks
                """
            },
            strategy="dialectical",
            total_tokens=1500,
            total_cost=0.015,
            success=True,
        )

        # Mock the query method
        self.multi_agent_client.query.side_effect = [
            thesis_response,
            antithesis_response,
            synthesis_response,
        ]

        # Run validation
        result = self.validator.validate_roadmap(
            self.ideation_result, project_goals=["Test goal"]
        )

        # Verify result structure
        self.assertIsInstance(result, ValidatedRoadmap)
        self.assertEqual(result.original_roadmap, self.roadmap)
        self.assertIsInstance(result.dialectical_validation, DialecticalValidation)
        self.assertGreater(len(result.validated_proposals), 0)
        self.assertGreater(result.overall_confidence, 0.0)
        self.assertGreater(result.total_cost, 0.0)

        # Verify multi-agent client was called 3 times (thesis, antithesis, synthesis)
        self.assertEqual(self.multi_agent_client.query.call_count, 3)

        # Verify logger was called
        self.logger.info.assert_called()

    def test_proposal_validation_to_dict(self):
        """Test ProposalValidation to_dict conversion."""
        validation = ProposalValidation(
            proposal_id="test-1",
            decision=ValidationDecision.APPROVED,
            confidence=0.9,
            criteria_scores={
                ValidationCriterion.ALIGNMENT: 0.95,
                ValidationCriterion.FEASIBILITY: 0.85,
            },
            strengths=["Well designed"],
            concerns=["Complex"],
            risks=["Timeline"],
            suggestions=["Add tests"],
            alternatives=["Alternative approach"],
            provider_opinions={"anthropic": "Approved"},
        )

        result = validation.to_dict()

        self.assertEqual(result["proposal_id"], "test-1")
        self.assertEqual(result["decision"], "approved")
        self.assertEqual(result["confidence"], 0.9)
        self.assertEqual(len(result["strengths"]), 1)
        self.assertIn("alignment", result["criteria_scores"])

    def test_dialectical_validation_to_dict(self):
        """Test DialecticalValidation to_dict conversion."""
        validation = DialecticalValidation(
            thesis="Initial analysis",
            antithesis="Critical analysis",
            synthesis="Refined recommendations",
            consensus_confidence=0.85,
            total_cost=0.05,
            total_tokens=5000,
            duration_seconds=30.5,
        )

        result = validation.to_dict()

        self.assertEqual(result["thesis"], "Initial analysis")
        self.assertEqual(result["antithesis"], "Critical analysis")
        self.assertEqual(result["synthesis"], "Refined recommendations")
        self.assertEqual(result["consensus_confidence"], 0.85)

    def test_validated_roadmap_to_dict(self):
        """Test ValidatedRoadmap to_dict conversion."""
        validation = ProposalValidation(
            proposal_id="test-1",
            decision=ValidationDecision.APPROVED,
            confidence=0.9,
        )

        dialectical = DialecticalValidation(
            thesis="Thesis",
            antithesis="Antithesis",
            synthesis="Synthesis",
            consensus_confidence=0.85,
            total_cost=0.05,
            total_tokens=5000,
            duration_seconds=30.0,
        )

        roadmap = ValidatedRoadmap(
            original_roadmap=self.roadmap,
            validated_proposals={"test-1": validation},
            dialectical_validation=dialectical,
            approved_proposals=[self.proposals[0]],
            rejected_proposals=[],
            needs_revision=[],
            refined_phases=[{"name": "Phase 1", "features": []}],
            overall_confidence=0.87,
            total_cost=0.05,
            total_tokens=5000,
            duration_seconds=30.0,
        )

        result = roadmap.to_dict()

        self.assertIn("original_roadmap", result)
        self.assertIn("validated_proposals", result)
        self.assertIn("dialectical_validation", result)
        self.assertEqual(len(result["approved_proposals"]), 1)
        self.assertEqual(result["overall_confidence"], 0.87)

    def test_validation_decision_enum(self):
        """Test ValidationDecision enum values."""
        self.assertEqual(ValidationDecision.APPROVED.value, "approved")
        self.assertEqual(
            ValidationDecision.APPROVED_WITH_CHANGES.value, "approved_with_changes"
        )
        self.assertEqual(ValidationDecision.NEEDS_REVISION.value, "needs_revision")
        self.assertEqual(ValidationDecision.REJECTED.value, "rejected")

    def test_validation_criterion_enum(self):
        """Test ValidationCriterion enum values."""
        self.assertEqual(ValidationCriterion.ALIGNMENT.value, "alignment")
        self.assertEqual(ValidationCriterion.FEASIBILITY.value, "feasibility")
        self.assertEqual(ValidationCriterion.PRIORITY.value, "priority")
        self.assertEqual(ValidationCriterion.SCOPE.value, "scope")
        self.assertEqual(ValidationCriterion.DEPENDENCIES.value, "dependencies")
        self.assertEqual(ValidationCriterion.VALUE.value, "value")


if __name__ == "__main__":
    unittest.main()
