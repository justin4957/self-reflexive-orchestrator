"""Main orchestrator that coordinates all operations."""

import time
from typing import Optional
from pathlib import Path

from .config import Config, ConfigManager
from .logger import AuditLogger, setup_logging, EventType
from .state import StateManager, OrchestratorState
from ..integrations.github_client import GitHubClient


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
                self.logger.info("Running in manual mode. Use CLI to trigger operations.")
                # Manual mode - wait for external triggers
                while self.running:
                    time.sleep(1)

            elif self.config.orchestrator.mode in ["supervised", "autonomous"]:
                # Autonomous/supervised mode - run main loop
                self._main_loop()

        except KeyboardInterrupt:
            self.logger.info("Received shutdown signal")
        except Exception as e:
            self.logger.error("Orchestrator encountered an error", error=str(e), exc_info=True)
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
                self.state_manager.transition_to(OrchestratorState.IDLE, "Monitoring cycle complete")

                # Sleep until next poll
                time.sleep(self.config.orchestrator.poll_interval)

            except Exception as e:
                self.logger.error("Error in main loop", error=str(e), exc_info=True)
                self.state_manager.transition_to(OrchestratorState.ERROR, str(e))
                time.sleep(60)  # Wait before retrying

    def _check_for_issues(self):
        """Check for new issues to process."""
        try:
            # Get issues with auto-claim labels
            issues = self.github.get_issues(
                labels=self.config.issue_processing.auto_claim_labels,
                exclude_labels=self.config.issue_processing.ignore_labels,
            )

            # Check concurrent limit
            in_progress = self.state_manager.get_in_progress_work_items("issue")
            if len(in_progress) >= self.config.issue_processing.max_concurrent:
                self.logger.debug(
                    "Max concurrent issues reached",
                    current=len(in_progress),
                    max=self.config.issue_processing.max_concurrent,
                )
                return

            # Process new issues
            for issue in issues:
                # Check if already being processed
                existing = self.state_manager.get_work_item("issue", str(issue.number))
                if existing:
                    continue

                # Add to work queue
                self.state_manager.add_work_item(
                    "issue",
                    str(issue.number),
                    metadata={
                        "title": issue.title,
                        "labels": [label.name for label in issue.labels],
                    },
                )

                self.logger.issue_claimed(issue.number, issue.title)

                # Check concurrent limit again
                if len(self.state_manager.get_in_progress_work_items("issue")) >= self.config.issue_processing.max_concurrent:
                    break

        except Exception as e:
            self.logger.error("Error checking for issues", error=str(e), exc_info=True)

    def _check_work_progress(self):
        """Check progress of in-progress work items."""
        # This is a placeholder for Phase 2
        # Will implement actual issue processing, PR monitoring, etc.
        pass

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
        return {
            "state": self.state_manager.get_current_state().value,
            "mode": self.config.orchestrator.mode,
            "repository": self.config.github.repository,
            "running": self.running,
            "work_summary": self.state_manager.get_state_summary(),
        }
