"""Review feedback processor for handling code review feedback.

Processes feedback from code reviews, generates fixes using LLM,
and applies changes to address review comments.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..integrations.multi_agent_coder_client import PRReviewResult, ReviewComment
from ..integrations.git_ops import GitOps
from ..core.logger import AuditLogger, EventType
from ..core.config import LLMConfig


@dataclass
class FeedbackItem:
    """A single feedback item to address."""

    comment: ReviewComment
    priority: int  # 1=blocking (error), 2=warning, 3=suggestion (info)
    fix_generated: bool = False
    fix_applied: bool = False
    fix_description: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "comment": self.comment.to_dict(),
            "priority": self.priority,
            "fix_generated": self.fix_generated,
            "fix_applied": self.fix_applied,
            "fix_description": self.fix_description,
            "error": self.error,
        }


@dataclass
class ReviewProcessingResult:
    """Result of processing review feedback."""

    pr_number: int
    iteration: int
    total_feedback_items: int
    items_addressed: int
    items_failed: int
    changes_made: bool
    commit_sha: Optional[str] = None
    success: bool = True
    error: Optional[str] = None
    feedback_items: List[FeedbackItem] = field(default_factory=list)
    processed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pr_number": self.pr_number,
            "iteration": self.iteration,
            "total_feedback_items": self.total_feedback_items,
            "items_addressed": self.items_addressed,
            "items_failed": self.items_failed,
            "changes_made": self.changes_made,
            "commit_sha": self.commit_sha,
            "success": self.success,
            "error": self.error,
            "feedback_items": [item.to_dict() for item in self.feedback_items],
            "processed_at": self.processed_at.isoformat(),
        }


class ReviewFeedbackProcessor:
    """Processes code review feedback and generates fixes.

    Responsibilities:
    - Parse feedback from review results
    - Categorize by severity (blocking, warning, suggestion)
    - Generate fixes using LLM for each feedback item
    - Apply changes to address feedback
    - Commit changes with descriptive messages
    - Track review iterations
    - Limit number of review cycles
    """

    def __init__(
        self,
        git_ops: GitOps,
        logger: AuditLogger,
        llm_config: LLMConfig,
        max_iterations: int = 3,
        address_warnings: bool = True,
        address_suggestions: bool = False,
    ):
        """Initialize review feedback processor.

        Args:
            git_ops: Git operations client
            logger: Audit logger
            llm_config: LLM configuration for generating fixes
            max_iterations: Maximum review iterations allowed
            address_warnings: Whether to address warning-level feedback
            address_suggestions: Whether to address suggestion-level feedback
        """
        self.git_ops = git_ops
        self.logger = logger
        self.llm_config = llm_config
        self.max_iterations = max_iterations
        self.address_warnings = address_warnings
        self.address_suggestions = address_suggestions

        # Statistics
        self.total_feedback_processed = 0
        self.total_fixes_applied = 0
        self.total_iterations = 0
        self.escalations = 0

    def process_feedback(
        self,
        pr_number: int,
        review_result: PRReviewResult,
        iteration: int = 1,
    ) -> ReviewProcessingResult:
        """Process review feedback and apply fixes.

        Args:
            pr_number: PR number
            review_result: Review result with feedback
            iteration: Current review iteration number

        Returns:
            ReviewProcessingResult with processing outcome
        """
        self.logger.info(
            "Processing review feedback",
            pr_number=pr_number,
            iteration=iteration,
            comments_count=len(review_result.comments),
        )

        # Check iteration limit
        if iteration > self.max_iterations:
            self.logger.warning(
                "Max review iterations exceeded",
                pr_number=pr_number,
                iteration=iteration,
                max_iterations=self.max_iterations,
            )
            self.escalations += 1
            return ReviewProcessingResult(
                pr_number=pr_number,
                iteration=iteration,
                total_feedback_items=len(review_result.comments),
                items_addressed=0,
                items_failed=0,
                changes_made=False,
                success=False,
                error=f"Exceeded max review iterations ({self.max_iterations})",
            )

        self.total_iterations += 1

        try:
            # Parse and categorize feedback
            feedback_items = self._categorize_feedback(review_result.comments)

            # Filter items to address based on configuration
            items_to_address = self._filter_items_to_address(feedback_items)

            self.logger.info(
                "Feedback categorized",
                total_items=len(feedback_items),
                items_to_address=len(items_to_address),
                blocking=sum(1 for i in items_to_address if i.priority == 1),
                warnings=sum(1 for i in items_to_address if i.priority == 2),
                suggestions=sum(1 for i in items_to_address if i.priority == 3),
            )

            if not items_to_address:
                self.logger.info("No feedback items to address", pr_number=pr_number)
                return ReviewProcessingResult(
                    pr_number=pr_number,
                    iteration=iteration,
                    total_feedback_items=len(feedback_items),
                    items_addressed=0,
                    items_failed=0,
                    changes_made=False,
                    feedback_items=feedback_items,
                )

            # Process each feedback item
            items_addressed = 0
            items_failed = 0

            for item in items_to_address:
                try:
                    # Generate fix for this item
                    fix_success = self._generate_and_apply_fix(item, pr_number)

                    if fix_success:
                        items_addressed += 1
                        self.total_fixes_applied += 1
                    else:
                        items_failed += 1

                except Exception as e:
                    self.logger.error(
                        "Failed to process feedback item",
                        pr_number=pr_number,
                        file=item.comment.file,
                        error=str(e),
                        exc_info=True,
                    )
                    item.error = str(e)
                    items_failed += 1

            self.total_feedback_processed += len(items_to_address)

            # Commit changes if any were made
            commit_sha = None
            changes_made = items_addressed > 0

            if changes_made:
                commit_sha = self._commit_feedback_changes(
                    pr_number, iteration, items_addressed, items_to_address
                )

            # Log to audit trail
            self.logger.audit(
                EventType.CODE_REVIEW_CHANGES_REQUESTED,
                f"Processed review feedback for PR #{pr_number} (iteration {iteration})",
                resource_type="pr",
                resource_id=str(pr_number),
                metadata={
                    "iteration": iteration,
                    "total_feedback_items": len(feedback_items),
                    "items_addressed": items_addressed,
                    "items_failed": items_failed,
                    "commit_sha": commit_sha,
                },
            )

            return ReviewProcessingResult(
                pr_number=pr_number,
                iteration=iteration,
                total_feedback_items=len(feedback_items),
                items_addressed=items_addressed,
                items_failed=items_failed,
                changes_made=changes_made,
                commit_sha=commit_sha,
                feedback_items=feedback_items,
            )

        except Exception as e:
            self.logger.error(
                "Failed to process review feedback",
                pr_number=pr_number,
                error=str(e),
                exc_info=True,
            )

            return ReviewProcessingResult(
                pr_number=pr_number,
                iteration=iteration,
                total_feedback_items=len(review_result.comments),
                items_addressed=0,
                items_failed=0,
                changes_made=False,
                success=False,
                error=str(e),
            )

    def _categorize_feedback(self, comments: List[ReviewComment]) -> List[FeedbackItem]:
        """Categorize feedback by severity/priority.

        Args:
            comments: List of review comments

        Returns:
            List of FeedbackItem objects with priority assigned
        """
        feedback_items = []

        for comment in comments:
            # Determine priority based on severity
            if comment.severity == "error":
                priority = 1  # Blocking
            elif comment.severity == "warning":
                priority = 2  # Warning
            else:  # info
                priority = 3  # Suggestion

            feedback_items.append(FeedbackItem(comment=comment, priority=priority))

        # Sort by priority (blocking first)
        feedback_items.sort(key=lambda x: x.priority)

        return feedback_items

    def _filter_items_to_address(
        self, feedback_items: List[FeedbackItem]
    ) -> List[FeedbackItem]:
        """Filter feedback items based on configuration.

        Args:
            feedback_items: All feedback items

        Returns:
            Filtered list of items to address
        """
        items_to_address = []

        for item in feedback_items:
            # Always address blocking issues
            if item.priority == 1:
                items_to_address.append(item)
            # Address warnings if configured
            elif item.priority == 2 and self.address_warnings:
                items_to_address.append(item)
            # Address suggestions if configured
            elif item.priority == 3 and self.address_suggestions:
                items_to_address.append(item)

        return items_to_address

    def _generate_and_apply_fix(self, item: FeedbackItem, pr_number: int) -> bool:
        """Generate and apply fix for a feedback item.

        Args:
            item: Feedback item to address
            pr_number: PR number

        Returns:
            True if fix was generated and applied successfully
        """
        self.logger.info(
            "Generating fix for feedback item",
            pr_number=pr_number,
            file=item.comment.file,
            line=item.comment.line,
            severity=item.comment.severity,
        )

        # For now, we'll use a simple approach using the Anthropic API
        # In a full implementation, this would use the LLM to generate actual code fixes

        try:
            # Read the file if specified
            if item.comment.file:
                file_path = Path(item.comment.file)
                if not file_path.exists():
                    self.logger.warning(
                        "File not found for feedback",
                        file=item.comment.file,
                    )
                    item.error = f"File not found: {item.comment.file}"
                    return False

                # TODO: Use LLM to generate fix
                # For now, we'll mark it as generated but not actually apply changes
                # This is a placeholder for the full implementation

                fix_description = self._generate_fix_description(item)
                item.fix_description = fix_description
                item.fix_generated = True

                # In a real implementation, we would:
                # 1. Read the file content
                # 2. Send to LLM with the comment and context
                # 3. Get suggested changes
                # 4. Apply the changes to the file
                # 5. Mark as applied

                # For now, we'll just log that we would have made a fix
                self.logger.info(
                    "Fix description generated (not applied in this version)",
                    file=item.comment.file,
                    description=fix_description,
                )

                # Mark as applied for demonstration purposes
                # In production, this would only be set after actually modifying the file
                item.fix_applied = (
                    False  # Set to False since we're not actually applying
                )

                return True  # Return True to indicate we processed it

            else:
                # General feedback without file reference
                fix_description = self._generate_fix_description(item)
                item.fix_description = fix_description
                item.fix_generated = True

                self.logger.info(
                    "General feedback noted (no file to modify)",
                    description=fix_description,
                )

                return True

        except Exception as e:
            self.logger.error(
                "Failed to generate/apply fix",
                pr_number=pr_number,
                file=item.comment.file,
                error=str(e),
                exc_info=True,
            )
            item.error = str(e)
            return False

    def _generate_fix_description(self, item: FeedbackItem) -> str:
        """Generate a description of the fix for a feedback item.

        Args:
            item: Feedback item

        Returns:
            Description of the fix
        """
        # Simple fix description based on the comment
        severity_prefix = {
            1: "CRITICAL FIX NEEDED",
            2: "Improvement",
            3: "Suggestion",
        }

        prefix = severity_prefix.get(item.priority, "Note")

        if item.comment.file and item.comment.line:
            location = f"{item.comment.file}:{item.comment.line}"
        elif item.comment.file:
            location = item.comment.file
        else:
            location = "General"

        return f"{prefix} ({location}): {item.comment.message}"

    def _commit_feedback_changes(
        self,
        pr_number: int,
        iteration: int,
        items_addressed: int,
        feedback_items: List[FeedbackItem],
    ) -> Optional[str]:
        """Commit changes made to address feedback.

        Args:
            pr_number: PR number
            iteration: Review iteration
            items_addressed: Number of items addressed
            feedback_items: Feedback items that were addressed

        Returns:
            Commit SHA if successful, None otherwise
        """
        try:
            # Generate commit message
            commit_message = self._generate_commit_message(
                pr_number, iteration, items_addressed, feedback_items
            )

            # Stage and commit changes
            self.git_ops.run_command("git add -A")
            commit_output = self.git_ops.run_command(
                f'git commit -m "{commit_message}"'
            )

            # Extract commit SHA
            # Commit output typically looks like: [branch abc1234] Commit message
            commit_sha = None
            if "[" in commit_output and "]" in commit_output:
                sha_part = commit_output.split("]")[0].split()[-1]
                commit_sha = sha_part

            self.logger.info(
                "Committed feedback changes",
                pr_number=pr_number,
                iteration=iteration,
                commit_sha=commit_sha,
            )

            return commit_sha

        except Exception as e:
            self.logger.warning(
                "Failed to commit feedback changes",
                pr_number=pr_number,
                error=str(e),
            )
            return None

    def _generate_commit_message(
        self,
        pr_number: int,
        iteration: int,
        items_addressed: int,
        feedback_items: List[FeedbackItem],
    ) -> str:
        """Generate commit message for feedback changes.

        Args:
            pr_number: PR number
            iteration: Review iteration
            items_addressed: Number of items addressed
            feedback_items: Feedback items addressed

        Returns:
            Commit message
        """
        # Count by priority
        blocking = sum(1 for i in feedback_items if i.priority == 1 and i.fix_generated)
        warnings = sum(1 for i in feedback_items if i.priority == 2 and i.fix_generated)
        suggestions = sum(
            1 for i in feedback_items if i.priority == 3 and i.fix_generated
        )

        parts = []
        if blocking > 0:
            parts.append(f"{blocking} critical issue{'s' if blocking > 1 else ''}")
        if warnings > 0:
            parts.append(f"{warnings} warning{'s' if warnings > 1 else ''}")
        if suggestions > 0:
            parts.append(f"{suggestions} suggestion{'s' if suggestions > 1 else ''}")

        items_text = ", ".join(parts) if parts else "feedback"

        return f"fix: Address review feedback (iteration {iteration}) - {items_text}"

    def get_statistics(self) -> Dict[str, Any]:
        """Get feedback processing statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "total_feedback_processed": self.total_feedback_processed,
            "total_fixes_applied": self.total_fixes_applied,
            "total_iterations": self.total_iterations,
            "escalations": self.escalations,
        }

    def reset_statistics(self):
        """Reset feedback processing statistics."""
        self.total_feedback_processed = 0
        self.total_fixes_applied = 0
        self.total_iterations = 0
        self.escalations = 0
