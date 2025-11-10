"""Unit tests for IssueCreator."""

import unittest
from unittest.mock import MagicMock, Mock

from src.core.logger import AuditLogger
from src.cycles.issue_creator import (
    ComplexityLevel,
    CreatedIssue,
    IssueCategory,
    IssueCreationResult,
    IssueCreator,
)
from src.cycles.multi_agent_ideation import FeatureProposal, ProposalPriority
from src.cycles.roadmap_validator import (
    DialecticalValidation,
    ProposalValidation,
    SynthesizedRoadmap,
    ValidatedRoadmap,
    ValidationDecision,
)
from src.integrations.github_client import GitHubClient


class TestIssueCreator(unittest.TestCase):
    """Test cases for IssueCreator."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.github_client = Mock(spec=GitHubClient)

        self.creator = IssueCreator(
            github_client=self.github_client,
            logger=self.logger,
            auto_label=True,
            add_bot_approved=False,
        )

        # Create sample proposal
        self.proposal = FeatureProposal(
            id="test-1",
            title="Add Error Handling",
            description="Implement comprehensive error handling throughout the application",
            provider="anthropic",
            value_proposition="Reduce production errors by 40%",
            complexity_estimate=6,
            priority=ProposalPriority.HIGH,
            dependencies=["logging-system"],
            success_metrics=[
                "Error rate < 1%",
                "Mean time to recovery < 5 minutes",
            ],
            estimated_effort="2-3 weeks",
            category="reliability",
        )

        # Create sample validation
        self.validation = ProposalValidation(
            proposal_id="test-1",
            decision=ValidationDecision.APPROVED,
            confidence=0.9,
            strengths=["Well designed", "Clear value"],
            concerns=["Implementation complexity"],
            risks=["Timeline risk"],
            suggestions=["Add monitoring", "Include rollback plan"],
        )

    def test_initialization(self):
        """Test issue creator initialization."""
        self.assertEqual(self.creator.github_client, self.github_client)
        self.assertEqual(self.creator.logger, self.logger)
        self.assertTrue(self.creator.auto_label)
        self.assertFalse(self.creator.add_bot_approved)

    def test_priority_labels_defined(self):
        """Test that priority labels are defined."""
        self.assertIn(ProposalPriority.CRITICAL, IssueCreator.PRIORITY_LABELS)
        self.assertIn(ProposalPriority.HIGH, IssueCreator.PRIORITY_LABELS)
        self.assertIn(ProposalPriority.MEDIUM, IssueCreator.PRIORITY_LABELS)
        self.assertIn(ProposalPriority.LOW, IssueCreator.PRIORITY_LABELS)

    def test_category_mapping_defined(self):
        """Test that category mapping is defined."""
        self.assertIn("performance", IssueCreator.CATEGORY_MAPPING)
        self.assertIn("security", IssueCreator.CATEGORY_MAPPING)
        self.assertIn("reliability", IssueCreator.CATEGORY_MAPPING)

    def test_format_issue_title(self):
        """Test formatting issue title."""
        title = self.creator._format_issue_title(self.proposal)

        # Should keep existing title if it starts with action verb
        self.assertIn("Add Error Handling", title)

    def test_format_issue_title_adds_action_verb(self):
        """Test that action verb is added if missing."""
        proposal = FeatureProposal(
            id="test-2",
            title="Error Handling System",
            description="Test",
            provider="anthropic",
            value_proposition="Test",
            complexity_estimate=5,
            priority=ProposalPriority.MEDIUM,
        )

        title = self.creator._format_issue_title(proposal)

        # Should add "Implement" prefix
        self.assertTrue(title.startswith("Implement"))

    def test_format_issue_body(self):
        """Test formatting comprehensive issue body."""
        body = self.creator._format_issue_body(self.proposal, self.validation)

        # Check all required sections
        self.assertIn("## Description", body)
        self.assertIn(self.proposal.description, body)
        self.assertIn("## Rationale", body)
        self.assertIn(self.proposal.value_proposition, body)
        self.assertIn("## Benefits", body)
        self.assertIn("## Acceptance Criteria", body)
        self.assertIn("## Technical Notes", body)
        self.assertIn("6/10", body)  # complexity
        self.assertIn("2-3 weeks", body)  # effort
        self.assertIn("reliability", body)  # category
        self.assertIn("## Risks & Concerns", body)
        self.assertIn("## Implementation Suggestions", body)
        self.assertIn("Self-Reflexive Orchestrator", body)  # footer
        self.assertIn("90.0%", body)  # confidence

    def test_format_issue_body_without_validation(self):
        """Test formatting issue body without validation data."""
        body = self.creator._format_issue_body(self.proposal, None)

        # Should still have core sections
        self.assertIn("## Description", body)
        self.assertIn("## Rationale", body)
        self.assertIn("## Acceptance Criteria", body)
        self.assertIn("## Technical Notes", body)

        # Should not have validation-specific sections
        self.assertNotIn("## Benefits", body)
        self.assertNotIn("## Risks & Concerns", body)

    def test_determine_labels(self):
        """Test determining labels for issue."""
        labels = self.creator._determine_labels(self.proposal, self.validation)

        # Should include priority label
        self.assertIn("priority-high", labels)

        # Should include category label
        self.assertIn("reliability", labels)

        # Should include complexity label
        self.assertIn("complexity-medium", labels)  # complexity 6 = medium

        # Should not include bot-approved (disabled in setUp)
        self.assertNotIn("bot-approved", labels)

    def test_determine_labels_with_bot_approved(self):
        """Test labels with bot-approved enabled."""
        creator = IssueCreator(
            github_client=self.github_client,
            logger=self.logger,
            auto_label=True,
            add_bot_approved=True,
        )

        labels = creator._determine_labels(self.proposal, self.validation)

        self.assertIn("bot-approved", labels)

    def test_determine_labels_without_category(self):
        """Test labels when proposal has no category."""
        proposal = FeatureProposal(
            id="test-2",
            title="Test Feature",
            description="Test",
            provider="anthropic",
            value_proposition="Test",
            complexity_estimate=5,
            priority=ProposalPriority.MEDIUM,
            category=None,  # No category
        )

        labels = self.creator._determine_labels(proposal, None)

        # Should default to enhancement
        self.assertIn("enhancement", labels)

    def test_get_complexity_label_simple(self):
        """Test complexity label for simple tasks."""
        label = self.creator._get_complexity_label(2)
        self.assertEqual(label, ComplexityLevel.SIMPLE)

    def test_get_complexity_label_medium(self):
        """Test complexity label for medium tasks."""
        label = self.creator._get_complexity_label(5)
        self.assertEqual(label, ComplexityLevel.MEDIUM)

    def test_get_complexity_label_complex(self):
        """Test complexity label for complex tasks."""
        label = self.creator._get_complexity_label(9)
        self.assertEqual(label, ComplexityLevel.COMPLEX)

    def test_create_single_issue(self):
        """Test creating a single issue."""
        # Mock GitHub issue response
        mock_issue = MagicMock()
        mock_issue.number = 123
        mock_issue.html_url = "https://github.com/owner/repo/issues/123"

        self.github_client.create_issue.return_value = mock_issue

        # Create issue
        result = self.creator.create_single_issue(self.proposal, self.validation)

        # Verify issue was created
        self.github_client.create_issue.assert_called_once()

        # Check call arguments
        call_args = self.github_client.create_issue.call_args
        self.assertIn("Add Error Handling", call_args.kwargs["title"])
        self.assertIn("## Description", call_args.kwargs["body"])
        self.assertIsInstance(call_args.kwargs["labels"], list)

        # Check result
        self.assertIsInstance(result, CreatedIssue)
        self.assertEqual(result.issue_number, 123)
        self.assertEqual(result.proposal_id, "test-1")
        self.assertIn("github.com", result.url)

    def test_create_single_issue_with_custom_labels(self):
        """Test creating issue with custom labels."""
        mock_issue = MagicMock()
        mock_issue.number = 124
        mock_issue.html_url = "https://github.com/owner/repo/issues/124"

        self.github_client.create_issue.return_value = mock_issue

        custom_labels = ["custom-label", "test"]

        result = self.creator.create_single_issue(
            self.proposal, self.validation, labels=custom_labels
        )

        # Should use custom labels
        call_args = self.github_client.create_issue.call_args
        self.assertEqual(call_args.kwargs["labels"], custom_labels)

    def test_create_issues_from_roadmap(self):
        """Test creating issues from validated roadmap."""
        # Create validated roadmap
        proposal2 = FeatureProposal(
            id="test-2",
            title="Performance Optimization",
            description="Optimize database queries",
            provider="deepseek",
            value_proposition="Faster responses",
            complexity_estimate=7,
            priority=ProposalPriority.MEDIUM,
        )

        validation2 = ProposalValidation(
            proposal_id="test-2",
            decision=ValidationDecision.APPROVED,
            confidence=0.85,
        )

        validated_roadmap = ValidatedRoadmap(
            original_roadmap=SynthesizedRoadmap(
                phases=[],
                consensus_confidence=0.85,
                total_proposals_considered=10,
                selected_proposals=2,
                provider_perspectives={},
                synthesis_notes="",
            ),
            validated_proposals={
                "test-1": self.validation,
                "test-2": validation2,
            },
            dialectical_validation=DialecticalValidation(
                thesis="",
                antithesis="",
                synthesis="",
                consensus_confidence=0.85,
                total_cost=0.12,
                total_tokens=3000,
                duration_seconds=30.0,
            ),
            approved_proposals=[self.proposal, proposal2],
            rejected_proposals=[],
            needs_revision=[],
            refined_phases=[],
            overall_confidence=0.87,
            total_cost=0.12,
            total_tokens=3000,
            duration_seconds=30.0,
        )

        # Mock GitHub responses
        mock_issue1 = MagicMock()
        mock_issue1.number = 123
        mock_issue1.html_url = "https://github.com/owner/repo/issues/123"

        mock_issue2 = MagicMock()
        mock_issue2.number = 124
        mock_issue2.html_url = "https://github.com/owner/repo/issues/124"

        self.github_client.create_issue.side_effect = [mock_issue1, mock_issue2]

        # Create issues
        result = self.creator.create_issues_from_roadmap(validated_roadmap)

        # Verify results
        self.assertEqual(result.total_created, 2)
        self.assertEqual(result.total_skipped, 0)
        self.assertEqual(result.total_failed, 0)
        self.assertEqual(len(result.created_issues), 2)

        # Verify GitHub client was called twice
        self.assertEqual(self.github_client.create_issue.call_count, 2)

    def test_create_issues_from_roadmap_with_failures(self):
        """Test creating issues with some failures."""
        validated_roadmap = ValidatedRoadmap(
            original_roadmap=SynthesizedRoadmap(
                phases=[],
                consensus_confidence=0.85,
                total_proposals_considered=10,
                selected_proposals=1,
                provider_perspectives={},
                synthesis_notes="",
            ),
            validated_proposals={"test-1": self.validation},
            dialectical_validation=DialecticalValidation(
                thesis="",
                antithesis="",
                synthesis="",
                consensus_confidence=0.85,
                total_cost=0.12,
                total_tokens=3000,
                duration_seconds=30.0,
            ),
            approved_proposals=[self.proposal],
            rejected_proposals=[],
            needs_revision=[],
            refined_phases=[],
            overall_confidence=0.87,
            total_cost=0.12,
            total_tokens=3000,
            duration_seconds=30.0,
        )

        # Mock GitHub failure
        self.github_client.create_issue.side_effect = Exception("API Error")

        # Create issues
        result = self.creator.create_issues_from_roadmap(validated_roadmap)

        # Should track failure
        self.assertEqual(result.total_created, 0)
        self.assertEqual(result.total_failed, 1)
        self.assertIn("test-1", result.failed_proposals)

    def test_created_issue_to_dict(self):
        """Test CreatedIssue to_dict conversion."""
        issue = CreatedIssue(
            issue_number=123,
            title="Test Issue",
            proposal_id="test-1",
            url="https://github.com/owner/repo/issues/123",
            labels=["priority-high", "enhancement"],
        )

        result = issue.to_dict()

        self.assertEqual(result["issue_number"], 123)
        self.assertEqual(result["title"], "Test Issue")
        self.assertEqual(result["proposal_id"], "test-1")
        self.assertEqual(len(result["labels"]), 2)

    def test_issue_creation_result_to_dict(self):
        """Test IssueCreationResult to_dict conversion."""
        issue = CreatedIssue(
            issue_number=123,
            title="Test",
            proposal_id="test-1",
            url="https://github.com/test",
            labels=["test"],
        )

        result = IssueCreationResult(
            created_issues=[issue],
            skipped_proposals=["test-2"],
            failed_proposals=["test-3"],
            total_created=1,
            total_skipped=1,
            total_failed=1,
        )

        result_dict = result.to_dict()

        self.assertEqual(len(result_dict["created_issues"]), 1)
        self.assertEqual(len(result_dict["skipped_proposals"]), 1)
        self.assertEqual(len(result_dict["failed_proposals"]), 1)
        self.assertEqual(result_dict["total_created"], 1)

    def test_issue_category_enum(self):
        """Test IssueCategory enum values."""
        self.assertEqual(IssueCategory.ENHANCEMENT.value, "enhancement")
        self.assertEqual(IssueCategory.BUG.value, "bug")
        self.assertEqual(IssueCategory.REFACTOR.value, "refactor")
        self.assertEqual(IssueCategory.FEATURE.value, "feature")
        self.assertEqual(IssueCategory.PERFORMANCE.value, "performance")
        self.assertEqual(IssueCategory.SECURITY.value, "security")

    def test_complexity_level_enum(self):
        """Test ComplexityLevel enum values."""
        self.assertEqual(ComplexityLevel.SIMPLE.value, "complexity-simple")
        self.assertEqual(ComplexityLevel.MEDIUM.value, "complexity-medium")
        self.assertEqual(ComplexityLevel.COMPLEX.value, "complexity-complex")


if __name__ == "__main__":
    unittest.main()
