"""Complete roadmap cycle orchestration.

Integrates all Phase 4 components into end-to-end workflow:
- Roadmap scheduling
- Codebase analysis
- Multi-agent ideation
- Dialectical validation
- GitHub issue creation
"""

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.logger import AuditLogger
from ..cycles.issue_creator import IssueCreationResult, IssueCreator
from ..cycles.roadmap_generator import GeneratedRoadmap, RoadmapGenerator
from ..cycles.roadmap_scheduler import RoadmapScheduler
from ..cycles.roadmap_validator import RoadmapValidator, ValidatedRoadmap
from ..integrations.github_client import GitHubClient
from ..integrations.multi_agent_coder_client import MultiAgentCoderClient


@dataclass
class RoadmapCycleResult:
    """Result of complete roadmap cycle execution."""

    cycle_id: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float

    # Generated roadmap
    roadmap: GeneratedRoadmap

    # Validation results
    validated_roadmap: ValidatedRoadmap

    # Issue creation results
    issue_creation: IssueCreationResult

    # Costs and tokens
    total_cost: float
    total_tokens: int

    # Success metrics
    proposals_generated: int
    proposals_validated: int
    proposals_approved: int
    proposals_rejected: int
    issues_created: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "cycle_id": self.cycle_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "roadmap": self.roadmap.to_dict(),
            "validated_roadmap": self.validated_roadmap.to_dict(),
            "issue_creation": self.issue_creation.to_dict(),
            "total_cost": self.total_cost,
            "total_tokens": self.total_tokens,
            "proposals_generated": self.proposals_generated,
            "proposals_validated": self.proposals_validated,
            "proposals_approved": self.proposals_approved,
            "proposals_rejected": self.proposals_rejected,
            "issues_created": self.issues_created,
        }


class RoadmapCycle:
    """Orchestrates complete roadmap generation cycle.

    Responsibilities:
    - Coordinate all Phase 4 components
    - Execute end-to-end roadmap → issues workflow
    - Handle state transitions
    - Manage scheduling
    - Track costs and metrics
    - Handle errors gracefully
    - Log all operations
    """

    def __init__(
        self,
        repository_path: str,
        github_client: GitHubClient,
        multi_agent_client: MultiAgentCoderClient,
        logger: AuditLogger,
        scheduler_frequency: str = "weekly",
        auto_create_issues: bool = True,
        min_validation_confidence: float = 0.8,
    ):
        """Initialize roadmap cycle.

        Args:
            repository_path: Path to repository
            github_client: GitHub API client
            multi_agent_client: Multi-agent-coder client
            logger: Audit logger
            scheduler_frequency: Roadmap generation frequency
            auto_create_issues: Automatically create GitHub issues
            min_validation_confidence: Minimum confidence for approval
        """
        self.repository_path = Path(repository_path)
        self.github_client = github_client
        self.multi_agent_client = multi_agent_client
        self.logger = logger
        self.auto_create_issues = auto_create_issues
        self.min_validation_confidence = min_validation_confidence

        # Initialize components
        self.roadmap_generator = RoadmapGenerator(
            repository_path=str(self.repository_path),
            multi_agent_client=multi_agent_client,
            logger=logger,
        )

        self.roadmap_validator = RoadmapValidator(
            multi_agent_client=multi_agent_client,
            logger=logger,
            min_confidence=min_validation_confidence,
        )

        self.roadmap_scheduler = RoadmapScheduler(
            frequency=scheduler_frequency,
            logger=logger,
        )

        self.issue_creator = IssueCreator(
            github_client=github_client,
            logger=logger,
            auto_label=True,
            add_bot_approved=True,
        )

        self.logger.info(
            "roadmap_cycle_initialized",
            repository_path=str(self.repository_path),
            scheduler_frequency=scheduler_frequency,
            auto_create_issues=auto_create_issues,
            min_validation_confidence=min_validation_confidence,
        )

    def should_run_cycle(self, force: bool = False) -> bool:
        """Check if roadmap cycle should run.

        Args:
            force: Force execution regardless of schedule

        Returns:
            True if cycle should run
        """
        return self.roadmap_scheduler.should_generate_roadmap(force=force)

    def execute_cycle(
        self,
        project_goals: Optional[List[str]] = None,
        force: bool = False,
    ) -> RoadmapCycleResult:
        """Execute complete roadmap cycle.

        Args:
            project_goals: Optional project goals for context
            force: Force execution regardless of schedule

        Returns:
            RoadmapCycleResult with all outputs and metrics
        """
        cycle_id = (
            f"roadmap-cycle-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        )
        started_at = datetime.now(timezone.utc)

        self.logger.info(
            "roadmap_cycle_started",
            cycle_id=cycle_id,
            force=force,
            project_goals=project_goals,
        )

        try:
            # Step 1: Generate roadmap
            self.logger.info("roadmap_cycle_step_1", step="generate_roadmap")
            roadmap = self.roadmap_generator.generate_roadmap(
                roadmap_id=cycle_id,
                project_goals=project_goals,
                save_to_file=True,
            )

            # Step 2: Validate roadmap
            self.logger.info("roadmap_cycle_step_2", step="validate_roadmap")
            validated_roadmap = self.roadmap_validator.validate_roadmap(
                ideation_result=roadmap.ideation_result,
                project_goals=project_goals,
            )

            # Step 3: Create issues (if enabled)
            if self.auto_create_issues:
                self.logger.info("roadmap_cycle_step_3", step="create_issues")
                issue_creation = self.issue_creator.create_issues_from_roadmap(
                    validated_roadmap=validated_roadmap,
                    only_approved=True,
                    skip_existing=True,
                )
            else:
                self.logger.info(
                    "roadmap_cycle_step_3_skipped", reason="auto_create_issues_disabled"
                )
                issue_creation = IssueCreationResult(
                    created_issues=[],
                    skipped_proposals=[],
                    failed_proposals=[],
                    total_created=0,
                    total_skipped=0,
                    total_failed=0,
                )

            # Step 4: Mark cycle complete
            completed_at = datetime.now(timezone.utc)
            duration = (completed_at - started_at).total_seconds()

            self.roadmap_scheduler.mark_generation_complete(
                roadmap_id=cycle_id,
                generation_time=completed_at,
            )

            # Calculate totals
            total_cost = roadmap.metadata.total_cost + validated_roadmap.total_cost
            total_tokens = (
                roadmap.metadata.total_tokens + validated_roadmap.total_tokens
            )

            result = RoadmapCycleResult(
                cycle_id=cycle_id,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
                roadmap=roadmap,
                validated_roadmap=validated_roadmap,
                issue_creation=issue_creation,
                total_cost=total_cost,
                total_tokens=total_tokens,
                proposals_generated=len(roadmap.ideation_result.proposals),
                proposals_validated=len(validated_roadmap.validated_proposals),
                proposals_approved=len(validated_roadmap.approved_proposals),
                proposals_rejected=len(validated_roadmap.rejected_proposals),
                issues_created=issue_creation.total_created,
            )

            self.logger.info(
                "roadmap_cycle_completed",
                cycle_id=cycle_id,
                duration_seconds=duration,
                total_cost=total_cost,
                proposals_generated=result.proposals_generated,
                proposals_approved=result.proposals_approved,
                issues_created=result.issues_created,
            )

            return result

        except Exception as e:
            # Mark cycle as failed
            self.roadmap_scheduler.mark_generation_failed(str(e))

            self.logger.error(
                "roadmap_cycle_failed",
                cycle_id=cycle_id,
                error=str(e),
            )
            raise

    def get_schedule_status(self) -> Dict[str, Any]:
        """Get current schedule status.

        Returns:
            Dictionary with schedule information
        """
        return self.roadmap_scheduler.get_status()

    def get_last_roadmap_path(self) -> Optional[Path]:
        """Get path to last generated roadmap.

        Returns:
            Path to roadmap markdown file, or None if never generated
        """
        status = self.roadmap_scheduler.get_status()
        last_roadmap_id = status.get("last_roadmap_id")

        if not last_roadmap_id:
            return None

        roadmap_file = self.repository_path / "roadmaps" / f"{last_roadmap_id}.md"

        if roadmap_file.exists():
            return roadmap_file

        return None

    def reset_schedule(self):
        """Reset roadmap generation schedule."""
        self.roadmap_scheduler.reset_schedule()
        self.logger.info("roadmap_cycle_schedule_reset")
