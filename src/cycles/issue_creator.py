"""Issue creator that converts roadmap proposals into GitHub issues.

Creates comprehensive GitHub issues from validated roadmap proposals with:
- Detailed descriptions and rationale
- Benefits and acceptance criteria
- Technical notes and complexity estimates
- Risk assessments
- Appropriate labels and priority
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from ..core.logger import AuditLogger
from ..cycles.multi_agent_ideation import FeatureProposal, ProposalPriority
from ..cycles.roadmap_validator import ValidatedRoadmap, ValidationDecision
from ..integrations.github_client import GitHubClient


class IssueCategory(Enum):
    """Category labels for issues."""

    ENHANCEMENT = "enhancement"
    BUG = "bug"
    REFACTOR = "refactor"
    DOCUMENTATION = "documentation"
    FEATURE = "feature"
    PERFORMANCE = "performance"
    SECURITY = "security"
    RELIABILITY = "reliability"


class ComplexityLevel(Enum):
    """Complexity labels for issues."""

    SIMPLE = "complexity-simple"  # 1-3
    MEDIUM = "complexity-medium"  # 4-7
    COMPLEX = "complexity-complex"  # 8-10


@dataclass
class CreatedIssue:
    """Record of a created issue."""

    issue_number: int
    title: str
    proposal_id: str
    url: str
    labels: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "issue_number": self.issue_number,
            "title": self.title,
            "proposal_id": self.proposal_id,
            "url": self.url,
            "labels": self.labels,
        }


@dataclass
class IssueCreationResult:
    """Result of creating issues from roadmap."""

    created_issues: List[CreatedIssue]
    skipped_proposals: List[str]  # Proposal IDs that were skipped
    failed_proposals: List[str]  # Proposal IDs that failed to create
    total_created: int
    total_skipped: int
    total_failed: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "created_issues": [issue.to_dict() for issue in self.created_issues],
            "skipped_proposals": self.skipped_proposals,
            "failed_proposals": self.failed_proposals,
            "total_created": self.total_created,
            "total_skipped": self.total_skipped,
            "total_failed": self.total_failed,
        }


class IssueCreator:
    """Creates GitHub issues from validated roadmap proposals.

    Responsibilities:
    - Format proposals as comprehensive GitHub issues
    - Generate issue descriptions with all relevant information
    - Determine appropriate labels based on proposal attributes
    - Create issues via GitHub API
    - Track created issue numbers
    - Link related issues
    - Log all issue creation activities
    """

    # Priority label mapping
    PRIORITY_LABELS = {
        ProposalPriority.CRITICAL: "priority-critical",
        ProposalPriority.HIGH: "priority-high",
        ProposalPriority.MEDIUM: "priority-medium",
        ProposalPriority.LOW: "priority-low",
    }

    # Category mapping based on proposal category
    CATEGORY_MAPPING = {
        "performance": IssueCategory.PERFORMANCE,
        "security": IssueCategory.SECURITY,
        "reliability": IssueCategory.RELIABILITY,
        "documentation": IssueCategory.DOCUMENTATION,
        "refactor": IssueCategory.REFACTOR,
        "feature": IssueCategory.FEATURE,
    }

    def __init__(
        self,
        github_client: GitHubClient,
        logger: AuditLogger,
        auto_label: bool = True,
        add_bot_approved: bool = False,
    ):
        """Initialize issue creator.

        Args:
            github_client: GitHub API client
            logger: Audit logger
            auto_label: Automatically add labels based on proposal attributes
            add_bot_approved: Add 'bot-approved' label for auto-processing
        """
        self.github_client = github_client
        self.logger = logger
        self.auto_label = auto_label
        self.add_bot_approved = add_bot_approved

    def create_issues_from_roadmap(
        self,
        validated_roadmap: ValidatedRoadmap,
        only_approved: bool = True,
        skip_existing: bool = True,
    ) -> IssueCreationResult:
        """Create GitHub issues from validated roadmap.

        Args:
            validated_roadmap: Validated roadmap with proposals
            only_approved: Only create issues for approved proposals
            skip_existing: Skip proposals that already have issues

        Returns:
            IssueCreationResult with created issues and statistics
        """
        created_issues = []
        skipped_proposals = []
        failed_proposals = []

        # Determine which proposals to create issues for
        if only_approved:
            proposals_to_create = validated_roadmap.approved_proposals
        else:
            proposals_to_create = (
                validated_roadmap.approved_proposals + validated_roadmap.needs_revision
            )

        self.logger.info(
            "issue_creation_started",
            total_proposals=len(proposals_to_create),
            only_approved=only_approved,
        )

        for proposal in proposals_to_create:
            try:
                # Get validation for this proposal
                validation = validated_roadmap.validated_proposals.get(proposal.id)

                # Create issue
                created_issue = self._create_issue_for_proposal(proposal, validation)

                if created_issue:
                    created_issues.append(created_issue)
                    self.logger.info(
                        "issue_created",
                        proposal_id=proposal.id,
                        issue_number=created_issue.issue_number,
                        title=created_issue.title,
                    )
                else:
                    skipped_proposals.append(proposal.id)
                    self.logger.info("issue_skipped", proposal_id=proposal.id)

            except Exception as e:
                failed_proposals.append(proposal.id)
                self.logger.error(
                    "issue_creation_failed",
                    proposal_id=proposal.id,
                    error=str(e),
                )

        result = IssueCreationResult(
            created_issues=created_issues,
            skipped_proposals=skipped_proposals,
            failed_proposals=failed_proposals,
            total_created=len(created_issues),
            total_skipped=len(skipped_proposals),
            total_failed=len(failed_proposals),
        )

        self.logger.info(
            "issue_creation_completed",
            total_created=result.total_created,
            total_skipped=result.total_skipped,
            total_failed=result.total_failed,
        )

        return result

    def _create_issue_for_proposal(
        self, proposal: FeatureProposal, validation: Optional[Any] = None
    ) -> Optional[CreatedIssue]:
        """Create a single GitHub issue for a proposal.

        Args:
            proposal: Feature proposal to create issue for
            validation: Optional validation data for the proposal

        Returns:
            CreatedIssue if successful, None if skipped
        """
        # Format issue title
        title = self._format_issue_title(proposal)

        # Format issue body
        body = self._format_issue_body(proposal, validation)

        # Determine labels
        labels = self._determine_labels(proposal, validation)

        # Create issue via GitHub API
        issue = self.github_client.create_issue(
            title=title,
            body=body,
            labels=labels,
        )

        return CreatedIssue(
            issue_number=issue.number,
            title=title,
            proposal_id=proposal.id,
            url=issue.html_url,
            labels=labels,
        )

    def _format_issue_title(self, proposal: FeatureProposal) -> str:
        """Format issue title from proposal.

        Args:
            proposal: Feature proposal

        Returns:
            Formatted title
        """
        # Clean up title - remove any "Implement" or "Add" prefixes if present
        title = proposal.title.strip()

        # Ensure title starts with action verb if not already
        action_verbs = [
            "implement",
            "add",
            "create",
            "build",
            "develop",
            "refactor",
            "optimize",
            "improve",
            "fix",
            "update",
        ]

        title_lower = title.lower()
        has_action = any(title_lower.startswith(verb) for verb in action_verbs)

        if not has_action:
            # Default to "Implement" for features
            title = f"Implement {title}"

        return title

    def _format_issue_body(
        self, proposal: FeatureProposal, validation: Optional[Any] = None
    ) -> str:
        """Format comprehensive issue body from proposal.

        Args:
            proposal: Feature proposal
            validation: Optional validation data

        Returns:
            Formatted markdown issue body
        """
        sections = []

        # Description
        sections.append("## Description\n")
        sections.append(f"{proposal.description}\n")

        # Rationale (Value Proposition)
        sections.append("\n## Rationale\n")
        sections.append(f"{proposal.value_proposition}\n")

        # Benefits
        if validation and hasattr(validation, "strengths") and validation.strengths:
            sections.append("\n## Benefits\n")
            for strength in validation.strengths:
                sections.append(f"- {strength}\n")

        # Acceptance Criteria
        sections.append("\n## Acceptance Criteria\n")

        # Use success metrics if available
        if proposal.success_metrics:
            for metric in proposal.success_metrics:
                sections.append(f"- [ ] {metric}\n")
        else:
            # Generate basic criteria
            sections.append(f"- [ ] Implement {proposal.title.lower()}\n")
            sections.append(f"- [ ] Add tests for new functionality\n")
            sections.append(f"- [ ] Update documentation\n")

        # Technical Notes
        sections.append("\n## Technical Notes\n")
        sections.append(
            f"- **Estimated complexity**: {proposal.complexity_estimate}/10\n"
        )

        if proposal.estimated_effort:
            sections.append(f"- **Estimated effort**: {proposal.estimated_effort}\n")

        if proposal.category:
            sections.append(f"- **Category**: {proposal.category}\n")

        # Dependencies
        if proposal.dependencies:
            sections.append(f"- **Dependencies**: {', '.join(proposal.dependencies)}\n")

        # Provider source
        sections.append(f"- **Proposed by**: {proposal.provider.upper()}\n")

        # Risks and Concerns
        if validation and hasattr(validation, "concerns") and validation.concerns:
            sections.append("\n## Risks & Concerns\n")
            for concern in validation.concerns:
                sections.append(f"- {concern}\n")

        if validation and hasattr(validation, "risks") and validation.risks:
            if not (hasattr(validation, "concerns") and validation.concerns):
                sections.append("\n## Risks & Concerns\n")
            for risk in validation.risks:
                sections.append(f"- {risk}\n")

        # Suggestions for improvement
        if validation and hasattr(validation, "suggestions") and validation.suggestions:
            sections.append("\n## Implementation Suggestions\n")
            for suggestion in validation.suggestions:
                sections.append(f"- {suggestion}\n")

        # Footer
        sections.append("\n---\n")
        sections.append("🤖 Generated by Self-Reflexive Orchestrator Roadmap Cycle\n")

        if validation and hasattr(validation, "confidence"):
            sections.append(f"**Validation Confidence**: {validation.confidence:.1%}\n")

        return "".join(sections)

    def _determine_labels(
        self, proposal: FeatureProposal, validation: Optional[Any] = None
    ) -> List[str]:
        """Determine appropriate labels for the issue.

        Args:
            proposal: Feature proposal
            validation: Optional validation data

        Returns:
            List of label names
        """
        labels = []

        if not self.auto_label:
            return labels

        # Priority label
        priority_label = self.PRIORITY_LABELS.get(proposal.priority)
        if priority_label:
            labels.append(priority_label)

        # Category label
        if proposal.category:
            category = self.CATEGORY_MAPPING.get(
                proposal.category.lower(), IssueCategory.ENHANCEMENT
            )
            labels.append(category.value)
        else:
            # Default to enhancement
            labels.append(IssueCategory.ENHANCEMENT.value)

        # Complexity label
        complexity_label = self._get_complexity_label(proposal.complexity_estimate)
        labels.append(complexity_label.value)

        # Bot-approved label if configured
        if self.add_bot_approved:
            labels.append("bot-approved")

        return labels

    def _get_complexity_label(self, complexity: int) -> ComplexityLevel:
        """Get complexity label based on complexity estimate.

        Args:
            complexity: Complexity estimate (1-10)

        Returns:
            ComplexityLevel enum
        """
        if complexity <= 3:
            return ComplexityLevel.SIMPLE
        elif complexity <= 7:
            return ComplexityLevel.MEDIUM
        else:
            return ComplexityLevel.COMPLEX

    def create_single_issue(
        self,
        proposal: FeatureProposal,
        validation: Optional[Any] = None,
        labels: Optional[List[str]] = None,
    ) -> CreatedIssue:
        """Create a single issue from a proposal.

        Args:
            proposal: Feature proposal
            validation: Optional validation data
            labels: Optional custom labels (overrides auto-labeling)

        Returns:
            CreatedIssue object
        """
        title = self._format_issue_title(proposal)
        body = self._format_issue_body(proposal, validation)

        if labels is None:
            labels = self._determine_labels(proposal, validation)

        issue = self.github_client.create_issue(
            title=title,
            body=body,
            labels=labels,
        )

        self.logger.info(
            "single_issue_created",
            proposal_id=proposal.id,
            issue_number=issue.number,
            title=title,
        )

        return CreatedIssue(
            issue_number=issue.number,
            title=title,
            proposal_id=proposal.id,
            url=issue.html_url,
            labels=labels,
        )
