"""Main orchestrator that coordinates all operations."""

import time
from pathlib import Path
from typing import Optional

from ..analyzers.ci_failure_analyzer import CIFailureAnalyzer
from ..analyzers.implementation_planner import ImplementationPlanner
from ..analyzers.issue_analyzer import IssueAnalyzer
from ..analyzers.test_failure_analyzer import TestFailureAnalyzer
from ..cycles.code_executor import CodeExecutor
from ..cycles.issue_cycle import IssueMonitor
from ..cycles.issue_processor import IssueProcessor, ProcessingConfig
from ..cycles.pr_cycle import PRCreator
from ..integrations.git_ops import GitOps
from ..integrations.github_client import GitHubClient
from ..integrations.multi_agent_coder_client import MultiAgentCoderClient
from ..integrations.test_runner import TestRunner
from .config import Config, ConfigManager
from .logger import AuditLogger, EventType, setup_logging
from .state import OrchestratorState, StateManager


class Orchestrator:
    """Main orchestrator for autonomous development workflow."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize orchestrator.

        Args:
            config_path: Path to configuration file
        """
        # Load configuration
        self.config_manager = ConfigManager(config_path)
        self.config: Config = self.config_manager.load()

        # Set up logging
        self.logger = setup_logging(
            log_level=self.config.logging.level,
            log_file=self.config.logging.file,
            audit_file=self.config.logging.audit_file,
            structured=self.config.logging.structured,
        )

        # Initialize state manager
        self.state_manager = StateManager()

        # Initialize GitHub client
        self.github = GitHubClient(
            token=self.config.github.token,
            repository=self.config.github.repository,
            logger=self.logger,
        )

        # Set up workspace
        self.workspace = Path(self.config.orchestrator.work_dir)
        self.workspace.mkdir(parents=True, exist_ok=True)

        # Initialize Phase 2 components
        self._initialize_phase2_components()

        # Running flag
        self.running = False

        self.logger.audit(
            EventType.ORCHESTRATOR_STARTED,
            f"Orchestrator started in {self.config.orchestrator.mode} mode",
            metadata={
                "mode": self.config.orchestrator.mode,
                "repository": self.config.github.repository,
            },
        )

    def start(self):
        """Start the orchestrator main loop."""
        self.running = True
        self.logger.info(
            "Starting orchestrator",
            mode=self.config.orchestrator.mode,
            repository=self.config.github.repository,
        )

        try:
            if self.config.orchestrator.mode == "manual":
                self.logger.info(
                    "Running in manual mode. Use CLI to trigger operations."
                )
                # Manual mode - wait for external triggers
                while self.running:
                    time.sleep(1)

            elif self.config.orchestrator.mode in ["supervised", "autonomous"]:
                # Autonomous/supervised mode - run main loop
                self._main_loop()

        except KeyboardInterrupt:
            self.logger.info("Received shutdown signal")
        except Exception as e:
            self.logger.error(
                "Orchestrator encountered an error", error=str(e), exc_info=True
            )
            raise
        finally:
            self.stop()

    def stop(self):
        """Stop the orchestrator."""
        self.running = False
        self.logger.audit(
            EventType.ORCHESTRATOR_STOPPED,
            "Orchestrator stopped",
        )
        self.logger.info("Orchestrator stopped")

    def _main_loop(self):
        """Main orchestrator loop."""
        self.logger.info(
            "Starting main loop",
            poll_interval=self.config.orchestrator.poll_interval,
        )

        while self.running:
            try:
                # Update state to monitoring
                self.state_manager.transition_to(
                    OrchestratorState.MONITORING,
                    "Starting monitoring cycle",
                )

                # Check for new issues
                self._check_for_issues()

                # Check on in-progress work
                self._check_work_progress()

                # Check if roadmap generation is due
                if self.config.roadmap.enabled:
                    self._check_roadmap_cycle()

                # Return to idle
                self.state_manager.transition_to(
                    OrchestratorState.IDLE, "Monitoring cycle complete"
                )

                # Sleep until next poll
                time.sleep(self.config.orchestrator.poll_interval)

            except Exception as e:
                self.logger.error("Error in main loop", error=str(e), exc_info=True)
                self.state_manager.transition_to(OrchestratorState.ERROR, str(e))
                time.sleep(60)  # Wait before retrying

    def _check_for_issues(self):
        """Check for new issues to process using IssueMonitor."""
        try:
            # Use IssueMonitor to check for and claim new issues
            claimed_items = self.issue_monitor.check_for_new_issues()

            if claimed_items:
                self.logger.info(
                    f"Claimed {len(claimed_items)} new issues",
                    count=len(claimed_items),
                )

        except Exception as e:
            self.logger.error("Error checking for issues", error=str(e), exc_info=True)

    def _initialize_phase2_components(self):
        """Initialize all Phase 2 components for issue processing workflow."""
        self.logger.info("Initializing Phase 2 components")

        # Initialize Git operations
        self.git_ops = GitOps(
            repo_path=self.workspace,
            logger=self.logger,
        )

        # Initialize multi-agent-coder client
        self.multi_agent_coder = MultiAgentCoderClient(
            executable_path=self.config.multi_agent_coder.executable_path,
            logger=self.logger,
            default_strategy=self.config.multi_agent_coder.default_strategy,
            default_providers=self.config.multi_agent_coder.default_providers,
            timeout=self.config.multi_agent_coder.query_timeout,
        )

        # Initialize test runner
        self.test_runner = TestRunner(
            project_root=self.workspace,
            logger=self.logger,
        )

        # Initialize analyzers
        self.issue_analyzer = IssueAnalyzer(
            multi_agent_coder=self.multi_agent_coder,
            logger=self.logger,
        )

        self.implementation_planner = ImplementationPlanner(
            multi_agent_coder=self.multi_agent_coder,
            github_client=self.github,
            logger=self.logger,
        )

        self.test_failure_analyzer = TestFailureAnalyzer(
            multi_agent_coder=self.multi_agent_coder,
            logger=self.logger,
        )

        self.ci_failure_analyzer = CIFailureAnalyzer(
            multi_agent_client=self.multi_agent_coder,
            logger=self.logger,
        )

        # Initialize execution components
        self.code_executor = CodeExecutor(
            git_ops=self.git_ops,
            multi_agent_client=self.multi_agent_coder,
            logger=self.logger,
            repo_path=self.workspace,
            enable_code_generation=self.config.issue_processing.enable_auto_implementation,
        )

        self.pr_creator = PRCreator(
            git_ops=self.git_ops,
            github_client=self.github,
            logger=self.logger,
            default_base_branch=self.config.github.base_branch,
        )

        # Initialize issue monitor
        self.issue_monitor = IssueMonitor(
            github_client=self.github,
            state_manager=self.state_manager,
            config=self.config,
            logger=self.logger,
        )

        # Initialize issue processor with configuration
        processing_config = ProcessingConfig(
            max_complexity=self.config.issue_processing.max_complexity,
            min_actionability_confidence=self.config.issue_processing.min_actionability_confidence,
            min_plan_confidence=self.config.issue_processing.min_plan_confidence,
            enable_auto_fix=self.config.issue_processing.enable_auto_fix,
            max_fix_attempts=self.config.issue_processing.max_auto_fix_attempts,
            min_fix_confidence=self.config.issue_processing.min_fix_confidence,
            require_tests_passing=self.config.issue_processing.require_tests_passing,
            analysis_timeout=self.config.issue_processing.analysis_timeout,
            planning_timeout=self.config.issue_processing.planning_timeout,
            execution_timeout=self.config.issue_processing.execution_timeout,
            test_timeout=self.config.issue_processing.test_timeout,
        )

        self.issue_processor = IssueProcessor(
            issue_analyzer=self.issue_analyzer,
            implementation_planner=self.implementation_planner,
            code_executor=self.code_executor,
            test_runner=self.test_runner,
            test_failure_analyzer=self.test_failure_analyzer,
            pr_creator=self.pr_creator,
            github_client=self.github,
            state_manager=self.state_manager,
            logger=self.logger,
            config=processing_config,
        )

        self.logger.info("Phase 2 components initialized successfully")

    def _check_work_progress(self):
        """Check progress of in-progress work items and process them through Phase 2 workflow."""
        try:
            # Get pending work items for issues
            pending_items = self.state_manager.get_pending_work_items("issue")

            if not pending_items:
                self.logger.debug("No pending work items to process")
                return

            self.logger.info(
                f"Processing {len(pending_items)} pending work items",
                count=len(pending_items),
            )

            # Process each pending work item
            for work_item in pending_items:
                try:
                    # Skip if auto-implementation is disabled
                    if not self.config.issue_processing.enable_auto_implementation:
                        self.logger.debug(
                            f"Auto-implementation disabled, skipping work item {work_item.item_id}",
                            work_item_id=work_item.item_id,
                        )
                        continue

                    # Update state to in_progress
                    work_item.state = "in_progress"
                    self.state_manager.update_work_item(work_item)

                    # Process through Phase 2 workflow
                    self.logger.info(
                        f"Processing work item {work_item.item_id} through Phase 2 workflow",
                        work_item_id=work_item.item_id,
                        issue_number=work_item.metadata.get(
                            "issue_number", work_item.item_id
                        ),
                    )

                    result = self.issue_processor.process_work_item(work_item)

                    # Log result
                    if result.success:
                        self.logger.info(
                            f"Successfully processed work item {work_item.item_id}",
                            work_item_id=work_item.item_id,
                            pr_created=result.pr_created,
                            pr_number=result.pr_number,
                            total_time=result.total_time,
                        )

                        # Update work item to completed
                        work_item.state = "completed"
                        self.state_manager.update_work_item(work_item)
                    else:
                        self.logger.warning(
                            f"Failed to process work item {work_item.item_id}",
                            work_item_id=work_item.item_id,
                            error=result.error,
                            final_stage=result.final_stage.value,
                        )

                        # Work item state already updated by issue_processor

                except Exception as e:
                    self.logger.error(
                        f"Error processing work item {work_item.item_id}",
                        work_item_id=work_item.item_id,
                        error=str(e),
                        exc_info=True,
                    )

                    # Mark as failed
                    work_item.state = "failed"
                    work_item.error = str(e)
                    self.state_manager.update_work_item(work_item)

        except Exception as e:
            self.logger.error(
                "Error in _check_work_progress",
                error=str(e),
                exc_info=True,
            )

    def _check_roadmap_cycle(self):
        """Check if roadmap generation is due."""
        # This is a placeholder for Phase 4
        # Will implement roadmap generation logic
        pass

    def process_issue_manually(self, issue_number: int) -> bool:
        """Manually trigger processing of a specific issue.

        Args:
            issue_number: Issue number to process

        Returns:
            True if processing started successfully
        """
        try:
            issue = self.github.get_issue(issue_number)

            # Add to work queue
            self.state_manager.add_work_item(
                "issue",
                str(issue_number),
                metadata={
                    "title": issue.title,
                    "labels": [label.name for label in issue.labels],
                    "manual_trigger": True,
                },
            )

            self.logger.issue_claimed(issue_number, issue.title)
            self.logger.info(
                f"Manually triggered processing for issue #{issue_number}",
                issue_number=issue_number,
            )

            return True

        except Exception as e:
            self.logger.error(
                f"Failed to process issue #{issue_number}",
                issue_number=issue_number,
                error=str(e),
            )
            return False

    def get_status(self) -> dict:
        """Get current orchestrator status.

        Returns:
            Dictionary with status information
        """
        status = {
            "state": self.state_manager.get_current_state().value,
            "mode": self.config.orchestrator.mode,
            "repository": self.config.github.repository,
            "running": self.running,
            "work_summary": self.state_manager.get_state_summary(),
        }

        # Add Phase 2 statistics if components are initialized
        if hasattr(self, "issue_processor"):
            status["phase2_stats"] = {
                "issue_monitor": self.issue_monitor.get_statistics(),
                "issue_processor": self.issue_processor.get_statistics(),
            }

        return status
