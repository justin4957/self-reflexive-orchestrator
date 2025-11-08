"""Code execution engine for implementing changes based on implementation plans."""

import os
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ..core.logger import AuditLogger, EventType
from ..core.state import WorkItem, OrchestratorState
from ..analyzers.implementation_planner import ImplementationPlan, ImplementationStep
from ..integrations.git_ops import GitOps, GitOpsError, CommitInfo
from ..integrations.multi_agent_coder_client import MultiAgentCoderClient, MultiAgentResponse, MultiAgentStrategy


class ExecutionStatus(Enum):
    """Status of code execution."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


@dataclass
class CodeChange:
    """Represents a code change to be applied."""
    file_path: str
    change_type: str  # "create", "modify", "delete"
    content: Optional[str] = None
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_path": self.file_path,
            "change_type": self.change_type,
            "content_length": len(self.content) if self.content else 0,
            "description": self.description,
        }


@dataclass
class StepExecution:
    """Tracks execution of an implementation step."""
    step: ImplementationStep
    status: ExecutionStatus
    changes_applied: List[CodeChange] = field(default_factory=list)
    commit_info: Optional[CommitInfo] = None
    validation_feedback: Optional[MultiAgentResponse] = None
    error_message: Optional[str] = None
    attempts: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "step_number": self.step.step_number,
            "description": self.step.description,
            "status": self.status.value,
            "changes_applied": [c.to_dict() for c in self.changes_applied],
            "commit_hash": self.commit_info.commit_hash if self.commit_info else None,
            "validation_passed": self.validation_feedback.success if self.validation_feedback else None,
            "error_message": self.error_message,
            "attempts": self.attempts,
        }


@dataclass
class ExecutionResult:
    """Result of plan execution."""
    plan: ImplementationPlan
    step_executions: List[StepExecution]
    overall_status: ExecutionStatus
    branch_name: str
    commits_created: List[CommitInfo]
    total_files_changed: int
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "issue_number": self.plan.issue_number,
            "overall_status": self.overall_status.value,
            "branch_name": self.branch_name,
            "steps_executed": len(self.step_executions),
            "steps_completed": sum(1 for se in self.step_executions if se.status == ExecutionStatus.COMPLETED),
            "commits_created": len(self.commits_created),
            "total_files_changed": self.total_files_changed,
            "has_errors": bool(self.errors),
            "error_count": len(self.errors),
        }


class CodeExecutor:
    """Executes implementation plans by generating and applying code changes.

    Responsibilities:
    - Create git branches for implementation
    - Generate code changes step-by-step
    - Apply changes to files (create/modify)
    - Validate code with multi-agent-coder before committing
    - Create incremental commits with descriptive messages
    - Handle failures with retry logic
    - Track execution progress
    """

    # Configuration
    MAX_RETRY_ATTEMPTS = 3
    ENABLE_VALIDATION = True
    VALIDATION_REQUIRED_FOR_COMMIT = False  # For now, validation is advisory

    def __init__(
        self,
        git_ops: GitOps,
        multi_agent_client: MultiAgentCoderClient,
        logger: AuditLogger,
        repo_path: str,
        enable_validation: bool = True,
    ):
        """Initialize code executor.

        Args:
            git_ops: Git operations manager
            multi_agent_client: Multi-agent-coder client for validation
            logger: Audit logger instance
            repo_path: Path to repository root
            enable_validation: Whether to enable multi-agent code validation
        """
        self.git_ops = git_ops
        self.multi_agent = multi_agent_client
        self.logger = logger
        self.repo_path = Path(repo_path).resolve()
        self.enable_validation = enable_validation

        # Statistics
        self.total_executions = 0
        self.successful_executions = 0
        self.failed_executions = 0

    def execute_plan(
        self,
        plan: ImplementationPlan,
        work_item: WorkItem,
    ) -> ExecutionResult:
        """Execute an implementation plan.

        Args:
            plan: ImplementationPlan to execute
            work_item: WorkItem being processed

        Returns:
            ExecutionResult with execution details
        """
        self.logger.info(
            "Starting plan execution",
            issue_number=plan.issue_number,
            steps=len(plan.implementation_steps),
            branch=plan.branch_name,
            event_type=EventType.EXECUTION_STARTED,
        )

        try:
            # Create branch
            branch_name = self._create_execution_branch(plan)

            # Execute each step
            step_executions = []
            commits_created = []
            total_files_changed = 0
            errors = []

            for step in plan.implementation_steps:
                step_execution = self._execute_step(
                    step=step,
                    plan=plan,
                    work_item=work_item,
                )

                step_executions.append(step_execution)

                if step_execution.status == ExecutionStatus.COMPLETED:
                    if step_execution.commit_info:
                        commits_created.append(step_execution.commit_info)
                        total_files_changed += len(step_execution.commit_info.files_changed)
                elif step_execution.status == ExecutionStatus.FAILED:
                    if step_execution.error_message:
                        errors.append(f"Step {step.step_number}: {step_execution.error_message}")

            # Determine overall status
            if all(se.status == ExecutionStatus.COMPLETED for se in step_executions):
                overall_status = ExecutionStatus.COMPLETED
                self.successful_executions += 1
            elif any(se.status == ExecutionStatus.FAILED for se in step_executions):
                overall_status = ExecutionStatus.FAILED
                self.failed_executions += 1
            else:
                overall_status = ExecutionStatus.IN_PROGRESS

            result = ExecutionResult(
                plan=plan,
                step_executions=step_executions,
                overall_status=overall_status,
                branch_name=branch_name,
                commits_created=commits_created,
                total_files_changed=total_files_changed,
                errors=errors,
            )

            self.total_executions += 1

            self.logger.info(
                "Plan execution completed",
                issue_number=plan.issue_number,
                status=overall_status.value,
                commits=len(commits_created),
                files_changed=total_files_changed,
                errors=len(errors),
                event_type=EventType.EXECUTION_COMPLETED,
            )

            return result

        except Exception as e:
            self.logger.error(
                "Plan execution failed with exception",
                issue_number=plan.issue_number,
                error=str(e),
                exc_info=True,
            )
            self.failed_executions += 1
            raise

    def _create_execution_branch(self, plan: ImplementationPlan) -> str:
        """Create git branch for execution.

        Args:
            plan: Implementation plan

        Returns:
            Name of created branch
        """
        try:
            # Check if branch already exists
            if self.git_ops.branch_exists(plan.branch_name):
                self.logger.warning(
                    "Branch already exists",
                    branch=plan.branch_name,
                )
                # Switch to existing branch
                self.git_ops.switch_branch(plan.branch_name)
                return plan.branch_name

            # Create new branch
            branch_name = self.git_ops.create_branch(plan.branch_name)
            return branch_name

        except GitOpsError as e:
            raise RuntimeError(f"Failed to create execution branch: {e}")

    def _execute_step(
        self,
        step: ImplementationStep,
        plan: ImplementationPlan,
        work_item: WorkItem,
    ) -> StepExecution:
        """Execute a single implementation step.

        Args:
            step: ImplementationStep to execute
            plan: Full implementation plan
            work_item: WorkItem being processed

        Returns:
            StepExecution with results
        """
        self.logger.info(
            "Executing implementation step",
            step_number=step.step_number,
            description=step.description,
            files=step.files_affected,
        )

        step_execution = StepExecution(
            step=step,
            status=ExecutionStatus.IN_PROGRESS,
        )

        for attempt in range(1, self.MAX_RETRY_ATTEMPTS + 1):
            step_execution.attempts = attempt

            try:
                # Generate code changes for this step
                changes = self._generate_code_changes(step, plan, work_item)
                step_execution.changes_applied = changes

                if not changes:
                    self.logger.warning(
                        "No code changes generated for step",
                        step_number=step.step_number,
                    )
                    step_execution.status = ExecutionStatus.COMPLETED
                    break

                # Apply changes to files
                self._apply_changes(changes)

                # Validate code if enabled
                if self.enable_validation:
                    validation = self._validate_changes(changes, step)
                    step_execution.validation_feedback = validation

                    if not validation.success:
                        self.logger.warning(
                            "Code validation failed",
                            step_number=step.step_number,
                            error=validation.error,
                        )
                        # For now, continue anyway (validation is advisory)

                # Create commit
                commit_message = self._generate_commit_message(step, plan, changes)
                file_paths = [c.file_path for c in changes]

                commit_info = self.git_ops.commit(
                    message=commit_message,
                    file_paths=file_paths,
                    add_signature=True,
                )

                step_execution.commit_info = commit_info
                step_execution.status = ExecutionStatus.COMPLETED

                self.logger.info(
                    "Step execution completed",
                    step_number=step.step_number,
                    commit=commit_info.commit_hash[:8],
                    files_changed=len(changes),
                )

                break  # Success, exit retry loop

            except Exception as e:
                error_msg = f"Attempt {attempt}/{self.MAX_RETRY_ATTEMPTS} failed: {str(e)}"
                self.logger.error(
                    "Step execution failed",
                    step_number=step.step_number,
                    attempt=attempt,
                    error=str(e),
                    exc_info=True,
                )

                if attempt >= self.MAX_RETRY_ATTEMPTS:
                    step_execution.status = ExecutionStatus.FAILED
                    step_execution.error_message = error_msg
                else:
                    # Retry
                    self.logger.info(
                        "Retrying step execution",
                        step_number=step.step_number,
                        attempt=attempt + 1,
                    )

        return step_execution

    def _generate_code_changes(
        self,
        step: ImplementationStep,
        plan: ImplementationPlan,
        work_item: WorkItem,
    ) -> List[CodeChange]:
        """Generate code changes for an implementation step.

        This is a placeholder that would integrate with an LLM to generate
        actual code. For now, it creates stub implementations.

        Args:
            step: ImplementationStep to implement
            plan: Full implementation plan
            work_item: WorkItem context

        Returns:
            List of CodeChange objects
        """
        changes = []

        # For each file mentioned in the step
        for file_path in step.files_affected:
            file_full_path = self.repo_path / file_path

            # Determine if file exists
            if file_full_path.exists():
                change_type = "modify"
                # Read existing content
                with open(file_full_path, 'r', encoding='utf-8') as f:
                    existing_content = f.read()

                # TODO: Use LLM to generate modifications
                # For now, add a placeholder comment
                new_content = existing_content + f"\n\n# Implementation for step {step.step_number}: {step.description}\n"
            else:
                change_type = "create"
                # TODO: Use LLM to generate new file content
                # For now, create stub
                new_content = f'''"""Auto-generated file for step {step.step_number}."""

# {step.description}

# TODO: Implement functionality
pass
'''

            changes.append(CodeChange(
                file_path=file_path,
                change_type=change_type,
                content=new_content,
                description=f"Step {step.step_number}: {step.description}",
            ))

        return changes

    def _apply_changes(self, changes: List[CodeChange]) -> None:
        """Apply code changes to files.

        Args:
            changes: List of CodeChange objects to apply
        """
        for change in changes:
            file_full_path = self.repo_path / change.file_path

            # Create parent directories if needed
            file_full_path.parent.mkdir(parents=True, exist_ok=True)

            # Write content
            if change.content is not None:
                with open(file_full_path, 'w', encoding='utf-8') as f:
                    f.write(change.content)

                self.logger.debug(
                    "Applied code change",
                    file=change.file_path,
                    type=change.change_type,
                    size=len(change.content),
                )

    def _validate_changes(
        self,
        changes: List[CodeChange],
        step: ImplementationStep,
    ) -> MultiAgentResponse:
        """Validate code changes using multi-agent-coder.

        Args:
            changes: List of code changes to validate
            step: Implementation step context

        Returns:
            MultiAgentResponse with validation feedback
        """
        # Build validation prompt
        code_snippets = []
        for change in changes:
            if change.content:
                code_snippets.append(f"**File: {change.file_path}** ({change.change_type})\n```python\n{change.content[:500]}\n```")

        prompt = f"""Review this code change for quality and correctness:

**Step**: {step.description}
**Complexity**: {step.estimated_complexity}/10

**Changes**:
{chr(10).join(code_snippets)}

**Focus Areas**:
- Code correctness
- Follows best practices
- Error handling
- Code style and readability
- Potential bugs

Provide brief feedback (2-3 sentences). Approve if code looks reasonable.
"""

        try:
            response = self.multi_agent.review_code(
                code=prompt,
                focus_areas=["correctness", "style", "best practices"],
            )

            self.logger.debug(
                "Code validation completed",
                providers=response.providers,
                success=response.success,
            )

            return response

        except Exception as e:
            self.logger.error(
                "Code validation failed",
                error=str(e),
                exc_info=True,
            )
            # Return failed response
            return MultiAgentResponse(
                providers=[],
                responses={},
                strategy="all",
                total_tokens=0,
                total_cost=0.0,
                success=False,
                error=str(e),
            )

    def _generate_commit_message(
        self,
        step: ImplementationStep,
        plan: ImplementationPlan,
        changes: List[CodeChange],
    ) -> str:
        """Generate commit message for step.

        Args:
            step: Implementation step
            plan: Full plan
            changes: Code changes being committed

        Returns:
            Formatted commit message
        """
        file_paths = [c.file_path for c in changes]

        return self.git_ops.generate_commit_message(
            issue_number=plan.issue_number,
            step_description=step.description,
            files_changed=file_paths,
        )

    def get_statistics(self) -> Dict[str, Any]:
        """Get execution statistics.

        Returns:
            Dictionary with execution statistics
        """
        return {
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "success_rate": (
                (self.successful_executions / self.total_executions * 100)
                if self.total_executions > 0
                else 0.0
            ),
            "multi_agent_stats": self.multi_agent.get_statistics() if self.enable_validation else {},
        }

    def reset_statistics(self):
        """Reset execution statistics."""
        self.total_executions = 0
        self.successful_executions = 0
        self.failed_executions = 0
        if self.enable_validation:
            self.multi_agent.reset_statistics()
