"""Issue processor - orchestrates complete issue-to-PR workflow.

This module integrates all Phase 2 components into a cohesive workflow:
Issue Monitor → Issue Analyzer → Implementation Planner →
Code Executor → Test Runner → Test Failure Analysis → PR Creator
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum

from ..core.logger import AuditLogger, EventType
from ..core.state import StateManager, WorkItem
from ..analyzers.issue_analyzer import IssueAnalyzer, IssueAnalysis
from ..analyzers.implementation_planner import ImplementationPlanner, ImplementationPlan
from ..analyzers.test_failure_analyzer import TestFailureAnalyzer, FailureAnalysis
from ..cycles.code_executor import CodeExecutor, ExecutionResult, ExecutionStatus
from ..cycles.pr_cycle import PRCreator, PRCreationResult
from ..integrations.test_runner import TestRunner, TestResult
from ..integrations.github_client import GitHubClient


class ProcessingStage(Enum):
    """Stages in the issue processing workflow."""
    ANALYZING = "analyzing"
    PLANNING = "planning"
    IMPLEMENTING = "implementing"
    TESTING = "testing"
    ANALYZING_FAILURES = "analyzing_failures"
    FIXING = "fixing"
    CREATING_PR = "creating_pr"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProcessingConfig:
    """Configuration for issue processing workflow."""
    # Analysis config
    max_complexity: int = 7
    min_actionability_confidence: float = 0.6

    # Planning config
    min_plan_confidence: float = 0.6

    # Execution config
    max_step_retries: int = 3
    enable_validation: bool = True

    # Testing config
    require_tests_passing: bool = True
    max_fix_attempts: int = 2
    min_fix_confidence: float = 0.6
    enable_auto_fix: bool = True

    # Timeouts (seconds)
    analysis_timeout: int = 300
    planning_timeout: int = 600
    execution_timeout: int = 1200
    test_timeout: int = 300


@dataclass
class ProcessingResult:
    """Result of processing a work item through the workflow."""
    work_item: WorkItem
    success: bool
    final_stage: ProcessingStage
    pr_created: bool = False
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None
    error: Optional[str] = None
    stages_completed: list = field(default_factory=list)
    total_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        result['final_stage'] = self.final_stage.value
        return result


class IssueProcessor:
    """Orchestrates the complete issue-to-PR workflow.

    Responsibilities:
    - Coordinate all Phase 2 components in sequence
    - Manage state transitions for work items
    - Handle errors and implement retry logic
    - Track processing metrics and timing
    - Provide detailed logging and audit trails
    """

    def __init__(
        self,
        issue_analyzer: IssueAnalyzer,
        implementation_planner: ImplementationPlanner,
        code_executor: CodeExecutor,
        test_runner: TestRunner,
        test_failure_analyzer: TestFailureAnalyzer,
        pr_creator: PRCreator,
        github_client: GitHubClient,
        state_manager: StateManager,
        logger: AuditLogger,
        config: Optional[ProcessingConfig] = None,
    ):
        """Initialize issue processor.

        Args:
            issue_analyzer: Component for analyzing issues
            implementation_planner: Component for generating implementation plans
            code_executor: Component for executing code changes
            test_runner: Component for running tests
            test_failure_analyzer: Component for analyzing test failures
            pr_creator: Component for creating pull requests
            github_client: GitHub API client
            state_manager: State manager for tracking work
            logger: Audit logger
            config: Processing configuration
        """
        self.issue_analyzer = issue_analyzer
        self.implementation_planner = implementation_planner
        self.code_executor = code_executor
        self.test_runner = test_runner
        self.test_failure_analyzer = test_failure_analyzer
        self.pr_creator = pr_creator
        self.github = github_client
        self.state = state_manager
        self.logger = logger
        self.config = config or ProcessingConfig()

        # Statistics
        self.total_processed = 0
        self.successful = 0
        self.failed = 0
        self.stages_stats = {stage: 0 for stage in ProcessingStage}

    def process_work_item(self, work_item: WorkItem) -> ProcessingResult:
        """Process a single work item through the complete workflow.

        Args:
            work_item: Work item to process

        Returns:
            ProcessingResult with outcome and details
        """
        start_time = datetime.now(timezone.utc)
        stages_completed = []

        self.logger.info(
            f"Starting workflow for issue #{work_item.metadata.get('issue_number', work_item.item_id)}",
            work_item_id=work_item.item_id,
        )

        try:
            # Stage 1: Analyze Issue
            analysis = self._analyze_issue(work_item)
            stages_completed.append(ProcessingStage.ANALYZING.value)

            if not analysis:
                return self._create_result(
                    work_item, False, ProcessingStage.ANALYZING,
                    stages_completed, start_time, "Analysis failed"
                )

            # Check if issue is actionable
            if not analysis.is_actionable:
                self._update_work_item_state(work_item, "rejected",
                    f"Not actionable: {analysis.actionability_reason}")
                return self._create_result(
                    work_item, False, ProcessingStage.ANALYZING,
                    stages_completed, start_time,
                    f"Issue not actionable: {analysis.actionability_reason}"
                )

            # Check complexity
            if analysis.complexity_score > self.config.max_complexity:
                self._update_work_item_state(work_item, "rejected",
                    f"Too complex: {analysis.complexity_score}/{self.config.max_complexity}")
                return self._create_result(
                    work_item, False, ProcessingStage.ANALYZING,
                    stages_completed, start_time,
                    f"Issue too complex: {analysis.complexity_score}"
                )

            # Stage 2: Generate Implementation Plan
            plan = self._generate_plan(work_item, analysis)
            stages_completed.append(ProcessingStage.PLANNING.value)

            if not plan:
                return self._create_result(
                    work_item, False, ProcessingStage.PLANNING,
                    stages_completed, start_time, "Planning failed"
                )

            # Check plan confidence
            if plan.consensus_confidence < self.config.min_plan_confidence:
                self._update_work_item_state(work_item, "rejected",
                    f"Low plan confidence: {plan.consensus_confidence:.2f}")
                return self._create_result(
                    work_item, False, ProcessingStage.PLANNING,
                    stages_completed, start_time,
                    f"Plan confidence too low: {plan.consensus_confidence:.2f}"
                )

            # Stage 3: Execute Implementation
            execution_result = self._execute_implementation(work_item, plan)
            stages_completed.append(ProcessingStage.IMPLEMENTING.value)

            if not execution_result or execution_result.status != ExecutionStatus.SUCCESS:
                error_msg = execution_result.error if execution_result else "Execution failed"
                return self._create_result(
                    work_item, False, ProcessingStage.IMPLEMENTING,
                    stages_completed, start_time, error_msg
                )

            # Stage 4: Run Tests (with potential auto-fix loop)
            test_result, pr_result = self._test_and_fix_loop(work_item, plan)

            if pr_result:
                # Successfully created PR
                stages_completed.append(ProcessingStage.CREATING_PR.value)
                stages_completed.append(ProcessingStage.COMPLETED.value)

                elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                self.successful += 1
                self.stages_stats[ProcessingStage.COMPLETED] += 1

                return ProcessingResult(
                    work_item=work_item,
                    success=True,
                    final_stage=ProcessingStage.COMPLETED,
                    pr_created=True,
                    pr_number=pr_result.pr_number,
                    pr_url=pr_result.pr_url,
                    stages_completed=stages_completed,
                    total_time=elapsed,
                )
            else:
                # Tests failed and couldn't fix
                return self._create_result(
                    work_item, False, ProcessingStage.TESTING,
                    stages_completed, start_time,
                    "Tests failed and auto-fix unsuccessful"
                )

        except Exception as e:
            self.logger.error(
                "Unexpected error processing work item",
                work_item_id=work_item.item_id,
                error=str(e),
                exc_info=True,
            )
            self._update_work_item_state(work_item, "failed", str(e))
            return self._create_result(
                work_item, False, ProcessingStage.FAILED,
                stages_completed, start_time, str(e)
            )
        finally:
            self.total_processed += 1

    def _analyze_issue(self, work_item: WorkItem) -> Optional[IssueAnalysis]:
        """Analyze issue for actionability and complexity.

        Args:
            work_item: Work item to analyze

        Returns:
            IssueAnalysis or None if failed
        """
        self._update_work_item_state(work_item, "analyzing")

        try:
            # Get GitHub issue object
            issue_number = work_item.metadata.get("issue_number", int(work_item.item_id))
            issue = self.github.get_issue(issue_number)

            # Run analysis
            analysis = self.issue_analyzer.analyze_issue(issue)

            # Store analysis in work item metadata
            work_item.metadata["analysis"] = {
                "issue_type": analysis.issue_type,
                "complexity_score": analysis.complexity_score,
                "is_actionable": analysis.is_actionable,
                "actionability_reason": analysis.actionability_reason,
                "key_requirements": analysis.key_requirements,
                "recommended_approach": analysis.recommended_approach,
                "confidence": analysis.consensus_confidence,
            }
            self.state.update_work_item(work_item)

            self.logger.info(
                f"Issue analysis complete for #{issue_number}",
                issue_number=issue_number,
                actionable=analysis.is_actionable,
                complexity=analysis.complexity_score,
            )

            return analysis

        except Exception as e:
            self.logger.error(
                "Failed to analyze issue",
                work_item_id=work_item.item_id,
                error=str(e),
                exc_info=True,
            )
            self._update_work_item_state(work_item, "failed", f"Analysis error: {str(e)}")
            return None

    def _generate_plan(self, work_item: WorkItem, analysis: IssueAnalysis) -> Optional[ImplementationPlan]:
        """Generate implementation plan for the issue.

        Args:
            work_item: Work item
            analysis: Issue analysis result

        Returns:
            ImplementationPlan or None if failed
        """
        self._update_work_item_state(work_item, "planning")

        try:
            # Get GitHub issue object
            issue_number = work_item.metadata.get("issue_number", int(work_item.item_id))
            issue = self.github.get_issue(issue_number)

            # Generate plan
            plan = self.implementation_planner.generate_plan(issue, analysis)

            # Store plan summary in work item metadata
            work_item.metadata["plan"] = {
                "branch_name": plan.branch_name,
                "files_to_modify": plan.files_to_modify,
                "files_to_create": plan.files_to_create,
                "total_steps": len(plan.implementation_steps),
                "complexity": plan.estimated_total_complexity,
                "confidence": plan.consensus_confidence,
            }
            self.state.update_work_item(work_item)

            self.logger.info(
                f"Implementation plan generated for #{issue_number}",
                issue_number=issue_number,
                steps=len(plan.implementation_steps),
                confidence=plan.consensus_confidence,
            )

            return plan

        except Exception as e:
            self.logger.error(
                "Failed to generate plan",
                work_item_id=work_item.item_id,
                error=str(e),
                exc_info=True,
            )
            self._update_work_item_state(work_item, "failed", f"Planning error: {str(e)}")
            return None

    def _execute_implementation(self, work_item: WorkItem, plan: ImplementationPlan) -> Optional[ExecutionResult]:
        """Execute the implementation plan.

        Args:
            work_item: Work item
            plan: Implementation plan to execute

        Returns:
            ExecutionResult or None if failed
        """
        self._update_work_item_state(work_item, "implementing")

        try:
            # Execute the plan
            result = self.code_executor.execute_plan(plan)

            # Store execution summary in work item metadata
            work_item.metadata["execution"] = {
                "status": result.status.value,
                "steps_completed": result.steps_completed,
                "total_steps": result.total_steps,
                "files_modified": len(result.files_modified),
                "commits": len(result.commits),
            }
            self.state.update_work_item(work_item)

            self.logger.info(
                f"Implementation executed for issue #{work_item.metadata.get('issue_number')}",
                status=result.status.value,
                steps_completed=result.steps_completed,
            )

            return result

        except Exception as e:
            self.logger.error(
                "Failed to execute implementation",
                work_item_id=work_item.item_id,
                error=str(e),
                exc_info=True,
            )
            self._update_work_item_state(work_item, "failed", f"Execution error: {str(e)}")
            return None

    def _test_and_fix_loop(
        self,
        work_item: WorkItem,
        plan: ImplementationPlan
    ) -> tuple[Optional[TestResult], Optional[PRCreationResult]]:
        """Run tests and attempt fixes if needed.

        Args:
            work_item: Work item
            plan: Implementation plan

        Returns:
            Tuple of (final_test_result, pr_result)
        """
        attempt = 0
        max_attempts = self.config.max_fix_attempts + 1  # Initial attempt + fixes

        while attempt < max_attempts:
            # Run tests
            self._update_work_item_state(work_item, "testing")
            test_result = self._run_tests(work_item)

            if not test_result:
                self.logger.error("Test runner failed")
                return None, None

            # Check if tests pass
            if test_result.success:
                self.logger.info(
                    f"Tests passing for issue #{work_item.metadata.get('issue_number')}",
                    passed=test_result.passed,
                    total=test_result.total_tests,
                )

                # Create PR
                pr_result = self._create_pr(work_item, plan, test_result)
                return test_result, pr_result

            # Tests failed - check if we should try to fix
            if attempt >= self.config.max_fix_attempts:
                self.logger.warning(
                    f"Max fix attempts reached for issue #{work_item.metadata.get('issue_number')}",
                    attempts=attempt,
                )
                self._update_work_item_state(
                    work_item, "failed",
                    f"Tests failed after {attempt} fix attempts"
                )
                return test_result, None

            if not self.config.enable_auto_fix:
                self.logger.info("Auto-fix disabled, skipping fix attempt")
                self._update_work_item_state(work_item, "failed", "Tests failed, auto-fix disabled")
                return test_result, None

            # Attempt to analyze and fix failures
            self.logger.info(
                f"Attempting to fix test failures (attempt {attempt + 1}/{self.config.max_fix_attempts})",
                failed=test_result.failed,
            )

            fixed = self._analyze_and_fix_failures(work_item, test_result, plan)

            if not fixed:
                self.logger.warning("Failed to apply fixes, stopping")
                self._update_work_item_state(work_item, "failed", "Fix analysis failed")
                return test_result, None

            attempt += 1

        # Exhausted all attempts
        self._update_work_item_state(work_item, "failed", "Tests failed after all fix attempts")
        return test_result, None

    def _run_tests(self, work_item: WorkItem) -> Optional[TestResult]:
        """Run tests for the implementation.

        Args:
            work_item: Work item

        Returns:
            TestResult or None if failed
        """
        try:
            # Run tests
            result = self.test_runner.run_tests()

            # Store test results in work item metadata
            work_item.metadata["test_results"] = {
                "total": result.total_tests,
                "passed": result.passed,
                "failed": result.failed,
                "skipped": result.skipped,
                "success": result.success,
            }
            self.state.update_work_item(work_item)

            return result

        except Exception as e:
            self.logger.error(
                "Failed to run tests",
                work_item_id=work_item.item_id,
                error=str(e),
                exc_info=True,
            )
            return None

    def _analyze_and_fix_failures(
        self,
        work_item: WorkItem,
        test_result: TestResult,
        plan: ImplementationPlan
    ) -> bool:
        """Analyze test failures and attempt fixes.

        Args:
            work_item: Work item
            test_result: Test results with failures
            plan: Implementation plan

        Returns:
            True if fixes were applied successfully
        """
        self._update_work_item_state(work_item, "analyzing_failures")

        try:
            # Analyze failures
            analysis = self.test_failure_analyzer.analyze_test_failures(
                test_result=test_result,
                changed_files=plan.files_to_create + plan.files_to_modify,
            )

            # Check if we have confident fix suggestions
            if not analysis or analysis.auto_fix_recommended < self.config.min_fix_confidence:
                self.logger.warning(
                    "Fix confidence too low",
                    confidence=analysis.auto_fix_recommended if analysis else 0,
                )
                return False

            # Apply fixes
            self._update_work_item_state(work_item, "fixing")

            # TODO: Implement fix application through CodeExecutor
            # For now, we log the fix suggestions
            self.logger.info(
                "Fix suggestions generated",
                num_suggestions=len(analysis.fix_suggestions),
                confidence=analysis.auto_fix_recommended,
            )

            # Store analysis in metadata
            work_item.metadata.setdefault("fix_attempts", []).append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "failures_analyzed": len(analysis.root_causes),
                "fixes_suggested": len(analysis.fix_suggestions),
                "confidence": analysis.auto_fix_recommended,
            })
            self.state.update_work_item(work_item)

            return True

        except Exception as e:
            self.logger.error(
                "Failed to analyze/fix failures",
                work_item_id=work_item.item_id,
                error=str(e),
                exc_info=True,
            )
            return False

    def _create_pr(
        self,
        work_item: WorkItem,
        plan: ImplementationPlan,
        test_result: Optional[TestResult]
    ) -> Optional[PRCreationResult]:
        """Create pull request for the implementation.

        Args:
            work_item: Work item
            plan: Implementation plan
            test_result: Test results

        Returns:
            PRCreationResult or None if failed
        """
        self._update_work_item_state(work_item, "creating_pr")

        try:
            # Create PR
            result = self.pr_creator.create_pr_from_work_item(
                work_item=work_item,
                plan=plan,
                test_result=test_result,
            )

            if result.success:
                # Store PR info in work item metadata
                work_item.metadata["pr"] = {
                    "number": result.pr_number,
                    "url": result.pr_url,
                    "branch": plan.branch_name,
                }
                self._update_work_item_state(work_item, "pr_created")
                self.state.update_work_item(work_item)

                self.logger.audit(
                    EventType.PR_CREATED,
                    f"Created PR #{result.pr_number} for issue #{work_item.metadata.get('issue_number')}",
                    resource_type="pr",
                    resource_id=str(result.pr_number),
                    metadata={"url": result.pr_url},
                )
            else:
                self._update_work_item_state(work_item, "failed", f"PR creation failed: {result.error}")

            return result

        except Exception as e:
            self.logger.error(
                "Failed to create PR",
                work_item_id=work_item.item_id,
                error=str(e),
                exc_info=True,
            )
            self._update_work_item_state(work_item, "failed", f"PR creation error: {str(e)}")
            return None

    def _update_work_item_state(self, work_item: WorkItem, state: str, error: Optional[str] = None):
        """Update work item state and error message.

        Args:
            work_item: Work item to update
            state: New state
            error: Optional error message
        """
        work_item.state = state
        if error:
            work_item.error = error
        work_item.updated_at = datetime.now(timezone.utc).isoformat()
        self.state.update_work_item(work_item)

    def _create_result(
        self,
        work_item: WorkItem,
        success: bool,
        final_stage: ProcessingStage,
        stages_completed: list,
        start_time: datetime,
        error: Optional[str] = None
    ) -> ProcessingResult:
        """Create a ProcessingResult.

        Args:
            work_item: Work item
            success: Whether processing succeeded
            final_stage: Final stage reached
            stages_completed: List of stages completed
            start_time: Processing start time
            error: Optional error message

        Returns:
            ProcessingResult
        """
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

        if not success:
            self.failed += 1

        self.stages_stats[final_stage] += 1

        return ProcessingResult(
            work_item=work_item,
            success=success,
            final_stage=final_stage,
            pr_created=False,
            error=error,
            stages_completed=stages_completed,
            total_time=elapsed,
        )

    def get_statistics(self) -> Dict[str, Any]:
        """Get processing statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "total_processed": self.total_processed,
            "successful": self.successful,
            "failed": self.failed,
            "success_rate": (self.successful / self.total_processed * 100) if self.total_processed > 0 else 0,
            "stages_stats": {k.value: v for k, v in self.stages_stats.items()},
        }

    def reset_statistics(self):
        """Reset processing statistics."""
        self.total_processed = 0
        self.successful = 0
        self.failed = 0
        self.stages_stats = {stage: 0 for stage in ProcessingStage}
