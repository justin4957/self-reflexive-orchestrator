"""Roadmap scheduler for periodic roadmap generation.

Manages scheduling of roadmap generation based on configured frequency,
tracks last generation time, and determines when next generation is due.
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
import json

from ..core.logger import AuditLogger


class GenerationFrequency(Enum):
    """Roadmap generation frequency options."""

    MANUAL = "manual"  # Only when explicitly triggered
    DAILY = "daily"  # Every 24 hours
    WEEKLY = "weekly"  # Once per week
    MONTHLY = "monthly"  # Once per month


@dataclass
class ScheduleState:
    """State of roadmap generation schedule."""

    last_generation_time: Optional[datetime] = None
    last_roadmap_id: Optional[str] = None
    next_scheduled_time: Optional[datetime] = None
    generation_count: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "last_generation_time": (
                self.last_generation_time.isoformat()
                if self.last_generation_time
                else None
            ),
            "last_roadmap_id": self.last_roadmap_id,
            "next_scheduled_time": (
                self.next_scheduled_time.isoformat()
                if self.next_scheduled_time
                else None
            ),
            "generation_count": self.generation_count,
            "last_error": self.last_error,
            "last_error_time": (
                self.last_error_time.isoformat() if self.last_error_time else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduleState":
        """Create from dictionary."""
        return cls(
            last_generation_time=(
                datetime.fromisoformat(data["last_generation_time"])
                if data.get("last_generation_time")
                else None
            ),
            last_roadmap_id=data.get("last_roadmap_id"),
            next_scheduled_time=(
                datetime.fromisoformat(data["next_scheduled_time"])
                if data.get("next_scheduled_time")
                else None
            ),
            generation_count=data.get("generation_count", 0),
            last_error=data.get("last_error"),
            last_error_time=(
                datetime.fromisoformat(data["last_error_time"])
                if data.get("last_error_time")
                else None
            ),
        )


class RoadmapScheduler:
    """Manages scheduling for periodic roadmap generation.

    Responsibilities:
    - Track last roadmap generation timestamp
    - Determine when next generation is due based on frequency
    - Prevent duplicate roadmap generations
    - Persist schedule state to disk
    - Support manual triggering
    - Handle scheduling errors gracefully
    - Log all scheduling decisions
    """

    # Frequency intervals in seconds
    FREQUENCY_INTERVALS = {
        GenerationFrequency.DAILY: timedelta(days=1),
        GenerationFrequency.WEEKLY: timedelta(weeks=1),
        GenerationFrequency.MONTHLY: timedelta(days=30),  # Approximate month
    }

    def __init__(
        self,
        frequency: str,
        logger: AuditLogger,
        state_file: Optional[str] = None,
    ):
        """Initialize roadmap scheduler.

        Args:
            frequency: Generation frequency (manual, daily, weekly, monthly)
            logger: Audit logger
            state_file: Path to state persistence file (default: ./state/roadmap_schedule.json)
        """
        self.frequency = GenerationFrequency(frequency)
        self.logger = logger
        self.state_file = Path(
            state_file if state_file else "./state/roadmap_schedule.json"
        )

        # Load or initialize state
        self.state = self._load_state()

        self.logger.info(
            "roadmap_scheduler_initialized",
            frequency=self.frequency.value,
            state_file=str(self.state_file),
            last_generation=(
                self.state.last_generation_time.isoformat()
                if self.state.last_generation_time
                else "never"
            ),
        )

    def should_generate_roadmap(self, force: bool = False) -> bool:
        """Determine if a roadmap should be generated now.

        Args:
            force: Force generation regardless of schedule

        Returns:
            True if roadmap should be generated
        """
        if force:
            self.logger.info("roadmap_generation_forced", reason="manual_trigger")
            return True

        # Manual mode - never auto-generate
        if self.frequency == GenerationFrequency.MANUAL:
            self.logger.info(
                "roadmap_generation_skipped", reason="manual_mode", frequency="manual"
            )
            return False

        # First generation
        if self.state.last_generation_time is None:
            self.logger.info(
                "roadmap_generation_due",
                reason="first_generation",
                frequency=self.frequency.value,
            )
            return True

        # Check if enough time has elapsed
        now = datetime.now(timezone.utc)
        elapsed = now - self.state.last_generation_time
        required_interval = self.FREQUENCY_INTERVALS[self.frequency]

        if elapsed >= required_interval:
            self.logger.info(
                "roadmap_generation_due",
                reason="interval_elapsed",
                frequency=self.frequency.value,
                elapsed_seconds=elapsed.total_seconds(),
                required_seconds=required_interval.total_seconds(),
            )
            return True

        # Not yet due
        time_until_next = required_interval - elapsed
        self.logger.info(
            "roadmap_generation_not_due",
            frequency=self.frequency.value,
            time_until_next_seconds=time_until_next.total_seconds(),
            next_scheduled_time=(now + time_until_next).isoformat(),
        )
        return False

    def mark_generation_complete(
        self, roadmap_id: str, generation_time: Optional[datetime] = None
    ):
        """Mark a roadmap generation as complete.

        Args:
            roadmap_id: ID of the generated roadmap
            generation_time: Time of generation (default: now)
        """
        if generation_time is None:
            generation_time = datetime.now(timezone.utc)

        self.state.last_generation_time = generation_time
        self.state.last_roadmap_id = roadmap_id
        self.state.generation_count += 1
        self.state.last_error = None
        self.state.last_error_time = None

        # Calculate next scheduled time
        if self.frequency != GenerationFrequency.MANUAL:
            interval = self.FREQUENCY_INTERVALS[self.frequency]
            self.state.next_scheduled_time = generation_time + interval
        else:
            self.state.next_scheduled_time = None

        self._save_state()

        self.logger.info(
            "roadmap_generation_marked_complete",
            roadmap_id=roadmap_id,
            generation_time=generation_time.isoformat(),
            generation_count=self.state.generation_count,
            next_scheduled_time=(
                self.state.next_scheduled_time.isoformat()
                if self.state.next_scheduled_time
                else None
            ),
        )

    def mark_generation_failed(self, error_message: str):
        """Mark a roadmap generation as failed.

        Args:
            error_message: Error message describing the failure
        """
        self.state.last_error = error_message
        self.state.last_error_time = datetime.now(timezone.utc)

        self._save_state()

        self.logger.error(
            "roadmap_generation_failed",
            error=error_message,
            error_time=self.state.last_error_time.isoformat(),
        )

    def get_time_until_next(self) -> Optional[timedelta]:
        """Get time until next scheduled generation.

        Returns:
            Timedelta until next generation, or None if manual mode or never generated
        """
        if self.frequency == GenerationFrequency.MANUAL:
            return None

        if self.state.last_generation_time is None:
            # First generation - due now
            return timedelta(0)

        now = datetime.now(timezone.utc)
        interval = self.FREQUENCY_INTERVALS[self.frequency]
        next_time = self.state.last_generation_time + interval

        time_until = next_time - now

        # Return 0 if already due
        return max(time_until, timedelta(0))

    def get_next_scheduled_time(self) -> Optional[datetime]:
        """Get next scheduled generation time.

        Returns:
            Datetime of next generation, or None if manual mode
        """
        if self.frequency == GenerationFrequency.MANUAL:
            return None

        if self.state.next_scheduled_time:
            return self.state.next_scheduled_time

        # Calculate from last generation
        if self.state.last_generation_time:
            interval = self.FREQUENCY_INTERVALS[self.frequency]
            return self.state.last_generation_time + interval

        # Never generated - due now
        return datetime.now(timezone.utc)

    def reset_schedule(self):
        """Reset schedule state (useful for testing or reconfiguration)."""
        self.state = ScheduleState()
        self._save_state()

        self.logger.info("roadmap_schedule_reset")

    def _load_state(self) -> ScheduleState:
        """Load schedule state from disk.

        Returns:
            ScheduleState object (new if file doesn't exist)
        """
        if not self.state_file.exists():
            self.logger.info(
                "roadmap_schedule_state_not_found",
                state_file=str(self.state_file),
                action="creating_new",
            )
            return ScheduleState()

        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)

            state = ScheduleState.from_dict(data)

            self.logger.info(
                "roadmap_schedule_state_loaded",
                state_file=str(self.state_file),
                generation_count=state.generation_count,
            )

            return state

        except Exception as e:
            self.logger.error(
                "roadmap_schedule_state_load_failed",
                state_file=str(self.state_file),
                error=str(e),
                action="creating_new",
            )
            return ScheduleState()

    def _save_state(self):
        """Save schedule state to disk."""
        try:
            # Ensure state directory exists
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.state_file, "w") as f:
                json.dump(self.state.to_dict(), f, indent=2)

            self.logger.info(
                "roadmap_schedule_state_saved",
                state_file=str(self.state_file),
            )

        except Exception as e:
            self.logger.error(
                "roadmap_schedule_state_save_failed",
                state_file=str(self.state_file),
                error=str(e),
            )

    def get_status(self) -> Dict[str, Any]:
        """Get current schedule status.

        Returns:
            Dictionary with schedule status information
        """
        time_until_next = self.get_time_until_next()
        next_scheduled = self.get_next_scheduled_time()

        return {
            "frequency": self.frequency.value,
            "last_generation_time": (
                self.state.last_generation_time.isoformat()
                if self.state.last_generation_time
                else None
            ),
            "last_roadmap_id": self.state.last_roadmap_id,
            "generation_count": self.state.generation_count,
            "next_scheduled_time": (
                next_scheduled.isoformat() if next_scheduled else None
            ),
            "time_until_next_seconds": (
                time_until_next.total_seconds() if time_until_next is not None else None
            ),
            "is_due": self.should_generate_roadmap(force=False),
            "last_error": self.state.last_error,
            "last_error_time": (
                self.state.last_error_time.isoformat()
                if self.state.last_error_time
                else None
            ),
        }
