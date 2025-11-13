"""Code execution engine for implementing changes based on implementation plans."""

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..analyzers.implementation_planner import ImplementationPlan, ImplementationStep
from ..core.logger import AuditLogger, EventType
from ..core.state import OrchestratorState, WorkItem
from ..integrations.git_ops import CommitInfo, GitOps, GitOpsError
from ..integrations.multi_agent_coder_client import (
    MultiAgentCoderClient,
    MultiAgentResponse,
    MultiAgentStrategy,
)


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
            "validation_passed": (
                self.validation_feedback.success if self.validation_feedback else None
            ),
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
            "steps_completed": sum(
                1
                for se in self.step_executions
                if se.status == ExecutionStatus.COMPLETED
            ),
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
        enable_code_generation: bool = True,
    ):
        """Initialize code executor.

        Args:
            git_ops: Git operations manager
            multi_agent_client: Multi-agent-coder client for code generation and validation
            logger: Audit logger instance
            repo_path: Path to repository root
            enable_validation: Whether to enable multi-agent code validation
            enable_code_generation: Whether to use multi-agent-coder for real code generation (vs placeholders)
        """
        self.git_ops = git_ops
        self.multi_agent = multi_agent_client
        self.logger = logger
        self.repo_path = Path(repo_path).resolve()
        self.enable_validation = enable_validation
        self.enable_code_generation = enable_code_generation

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
                        total_files_changed += len(
                            step_execution.commit_info.files_changed
                        )
                elif step_execution.status == ExecutionStatus.FAILED:
                    if step_execution.error_message:
                        errors.append(
                            f"Step {step.step_number}: {step_execution.error_message}"
                        )

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
                error_msg = (
                    f"Attempt {attempt}/{self.MAX_RETRY_ATTEMPTS} failed: {str(e)}"
                )
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

        Uses multi-agent-coder to generate actual working code based on the
        implementation step description and context.

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
                with open(file_full_path, "r", encoding="utf-8") as f:
                    existing_content = f.read()
            else:
                change_type = "create"
                existing_content = None

            # Generate code using multi-agent-coder if enabled
            if self.enable_code_generation:
                try:
                    new_content = self._generate_code_with_llm(
                        step=step,
                        file_path=file_path,
                        existing_content=existing_content,
                        plan=plan,
                        work_item=work_item,
                    )
                except Exception as e:
                    self.logger.error(
                        "Code generation failed, using placeholder",
                        file_path=file_path,
                        error=str(e),
                        exc_info=True,
                    )
                    # Fallback to placeholder
                    new_content = self._generate_placeholder_code(
                        step=step,
                        file_path=file_path,
                        existing_content=existing_content,
                    )
            else:
                # Use placeholder if code generation disabled
                new_content = self._generate_placeholder_code(
                    step=step,
                    file_path=file_path,
                    existing_content=existing_content,
                )

            changes.append(
                CodeChange(
                    file_path=file_path,
                    change_type=change_type,
                    content=new_content,
                    description=f"Step {step.step_number}: {step.description}",
                )
            )

        return changes

    def _generate_code_with_llm(
        self,
        step: ImplementationStep,
        file_path: str,
        existing_content: Optional[str],
        plan: ImplementationPlan,
        work_item: WorkItem,
    ) -> str:
        """Generate real code using multi-agent-coder.

        Args:
            step: Implementation step
            file_path: Path to file being generated/modified
            existing_content: Existing file content (None if new file)
            plan: Full implementation plan for context
            work_item: Work item being processed

        Returns:
            Generated code content

        Raises:
            RuntimeError: If code generation fails
        """
        # Build comprehensive prompt for code generation
        prompt = self._build_code_generation_prompt(
            step=step,
            file_path=file_path,
            existing_content=existing_content,
            plan=plan,
            work_item=work_item,
        )

        self.logger.info(
            "Generating code with multi-agent-coder",
            file_path=file_path,
            step_number=step.step_number,
            has_existing=existing_content is not None,
        )

        # Use single provider (anthropic) for deterministic code generation
        # All providers could have different coding styles which would be inconsistent
        response = self.multi_agent.query(
            prompt=prompt,
            strategy=MultiAgentStrategy.ALL,
            providers=["anthropic"],  # Use single provider for consistency
            timeout=180,  # 3 minutes for code generation
        )

        if not response.success:
            raise RuntimeError(f"Code generation failed: {response.error}")

        # Extract code from first successful provider response
        # Try providers in order, skip error responses
        generated_code = None
        successful_provider = None

        for provider in response.providers:
            if provider in response.responses:
                response_text = response.responses[provider]
                # Skip error responses (typically start with ANSI color codes for errors)
                if response_text and not response_text.startswith("\x1b[31mError:"):
                    generated_code = response_text
                    successful_provider = provider
                    self.logger.debug(
                        "Using code from provider",
                        provider=provider,
                        code_length=len(response_text),
                    )
                    break

        if not generated_code:
            # Log all provider responses for debugging
            for provider, resp in response.responses.items():
                self.logger.error(
                    "Provider response",
                    provider=provider,
                    response_preview=resp[:500] if resp else None,
                )
            raise RuntimeError("No code generated by any LLM provider")

        # Clean up the response (remove markdown code blocks if present)
        generated_code = self._clean_generated_code(generated_code)

        self.logger.info(
            "Code generation successful",
            file_path=file_path,
            provider=successful_provider,
            code_length=len(generated_code),
            tokens=response.total_tokens,
            cost=response.total_cost,
        )

        return generated_code

    def _build_code_generation_prompt(
        self,
        step: ImplementationStep,
        file_path: str,
        existing_content: Optional[str],
        plan: ImplementationPlan,
        work_item: WorkItem,
    ) -> str:
        """Build prompt for code generation.

        Args:
            step: Implementation step
            file_path: File path
            existing_content: Existing content if modifying
            plan: Implementation plan
            work_item: Work item

        Returns:
            Formatted prompt
        """
        # Get issue context
        issue_title = work_item.metadata.get("title", f"Issue #{work_item.item_id}")
        issue_description = work_item.metadata.get("description", "")

        if existing_content:
            prompt = f"""You are a Python code generator. Generate production-quality, working code.

ISSUE: {issue_title}
{issue_description}

IMPLEMENTATION STEP {step.step_number}/{len(plan.implementation_steps)}:
{step.description}

FILE TO MODIFY: {file_path}

EXISTING CODE:
```python
{existing_content}
```

DEPENDENCIES (for context):
{self._format_dependencies(step, plan)}

INSTRUCTIONS:
1. Modify the existing code to implement the requested step
2. Preserve all existing functionality unless it conflicts with requirements
3. Follow Python best practices and PEP 8
4. Add comprehensive docstrings (Google style)
5. Include type hints for all functions/methods
6. Add proper error handling
7. Ensure all code is complete and functional
8. DO NOT add explanatory text or markdown
9. Return ONLY the complete, modified file content

CRITICAL: Return raw Python code only. No markdown, no explanations, no code blocks."""

        else:
            prompt = f"""You are a Python code generator. Generate production-quality, working code.

ISSUE: {issue_title}
{issue_description}

IMPLEMENTATION STEP {step.step_number}/{len(plan.implementation_steps)}:
{step.description}

FILE TO CREATE: {file_path}

DEPENDENCIES (for context):
{self._format_dependencies(step, plan)}

INSTRUCTIONS:
1. Create a complete, working Python file
2. Include module-level docstring explaining purpose
3. Follow Python best practices and PEP 8
4. Add comprehensive docstrings (Google style)
5. Include type hints for all functions/methods
6. Add proper error handling
7. Include all necessary imports
8. Ensure all code is complete and functional
9. DO NOT add explanatory text or markdown
10. Return ONLY the complete file content

CRITICAL: Return raw Python code only. No markdown, no explanations, no code blocks."""

        return prompt

    def _format_dependencies(
        self, step: ImplementationStep, plan: ImplementationPlan
    ) -> str:
        """Format dependency information for context.

        Args:
            step: Current step
            plan: Full plan

        Returns:
            Formatted dependency string
        """
        parts = []

        if step.dependencies:
            parts.append(
                f"Dependencies: {', '.join(str(d) for d in step.dependencies)}"
            )

        if plan.files_to_create:
            parts.append(f"New files in plan: {', '.join(plan.files_to_create)}")

        if plan.files_to_modify:
            parts.append(f"Modified files in plan: {', '.join(plan.files_to_modify)}")

        return "\n".join(parts) if parts else "None"

    def _clean_generated_code(self, code: str) -> str:
        """Clean generated code by removing markdown artifacts.

        Args:
            code: Generated code (may have markdown)

        Returns:
            Cleaned code
        """
        # Remove markdown code blocks if present
        lines = code.strip().split("\n")

        # Check if wrapped in ```python or ```
        if lines[0].strip().startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]

        # Find minimum indentation (excluding empty lines)
        min_indent: float = float("inf")
        for line in lines:
            if line.strip():  # Skip empty lines
                leading_spaces = len(line) - len(line.lstrip())
                min_indent = min(min_indent, leading_spaces)

        # If all lines have common leading whitespace, strip it
        if min_indent > 0 and min_indent != float("inf"):
            min_indent_int = int(min_indent)
            lines = [
                line[min_indent_int:] if len(line) > min_indent_int else line
                for line in lines
            ]

        return "\n".join(lines)

    def _generate_placeholder_code(
        self,
        step: ImplementationStep,
        file_path: str,
        existing_content: Optional[str],
    ) -> str:
        """Generate placeholder code (fallback when LLM generation disabled/fails).

        Args:
            step: Implementation step
            file_path: File path
            existing_content: Existing content if any

        Returns:
            Placeholder code
        """
        if existing_content:
            # Add placeholder comment to existing file
            return (
                existing_content
                + f"\n\n# Implementation for step {step.step_number}: {step.description}\n"
            )
        else:
            # Create stub file
            return f'''"""Auto-generated file for step {step.step_number}."""

# {step.description}

# TODO: Implement functionality
pass
'''

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
                with open(file_full_path, "w", encoding="utf-8") as f:
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
                code_snippets.append(
                    f"**File: {change.file_path}** ({change.change_type})\n```python\n{change.content[:500]}\n```"
                )

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
            "multi_agent_stats": (
                self.multi_agent.get_statistics() if self.enable_validation else {}
            ),
        }

    def reset_statistics(self):
        """Reset execution statistics."""
        self.total_executions = 0
        self.successful_executions = 0
        self.failed_executions = 0
        if self.enable_validation:
            self.multi_agent.reset_statistics()
