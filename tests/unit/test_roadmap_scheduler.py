"""Unit tests for RoadmapScheduler."""

import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from src.core.logger import AuditLogger
from src.cycles.roadmap_scheduler import (GenerationFrequency,
                                          RoadmapScheduler, ScheduleState)


class TestRoadmapScheduler(unittest.TestCase):
    """Test cases for RoadmapScheduler."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)

        # Create temporary state directory
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "roadmap_schedule.json"

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir)

    def test_initialization_daily(self):
        """Test scheduler initialization with daily frequency."""
        scheduler = RoadmapScheduler(
            frequency="daily",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        self.assertEqual(scheduler.frequency, GenerationFrequency.DAILY)
        self.assertEqual(scheduler.state_file, self.state_file)
        self.assertIsNotNone(scheduler.state)

    def test_initialization_weekly(self):
        """Test scheduler initialization with weekly frequency."""
        scheduler = RoadmapScheduler(
            frequency="weekly",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        self.assertEqual(scheduler.frequency, GenerationFrequency.WEEKLY)

    def test_initialization_monthly(self):
        """Test scheduler initialization with monthly frequency."""
        scheduler = RoadmapScheduler(
            frequency="monthly",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        self.assertEqual(scheduler.frequency, GenerationFrequency.MONTHLY)

    def test_initialization_manual(self):
        """Test scheduler initialization with manual frequency."""
        scheduler = RoadmapScheduler(
            frequency="manual",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        self.assertEqual(scheduler.frequency, GenerationFrequency.MANUAL)

    def test_frequency_intervals_defined(self):
        """Test that frequency intervals are defined."""
        self.assertIn(GenerationFrequency.DAILY, RoadmapScheduler.FREQUENCY_INTERVALS)
        self.assertIn(GenerationFrequency.WEEKLY, RoadmapScheduler.FREQUENCY_INTERVALS)
        self.assertIn(GenerationFrequency.MONTHLY, RoadmapScheduler.FREQUENCY_INTERVALS)

        # Check interval values
        self.assertEqual(
            RoadmapScheduler.FREQUENCY_INTERVALS[GenerationFrequency.DAILY],
            timedelta(days=1),
        )
        self.assertEqual(
            RoadmapScheduler.FREQUENCY_INTERVALS[GenerationFrequency.WEEKLY],
            timedelta(weeks=1),
        )
        self.assertEqual(
            RoadmapScheduler.FREQUENCY_INTERVALS[GenerationFrequency.MONTHLY],
            timedelta(days=30),
        )

    def test_should_generate_roadmap_first_time(self):
        """Test that first generation is always due."""
        scheduler = RoadmapScheduler(
            frequency="daily",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        # First time - should be due
        self.assertTrue(scheduler.should_generate_roadmap())

    def test_should_generate_roadmap_manual_mode(self):
        """Test that manual mode never auto-generates."""
        scheduler = RoadmapScheduler(
            frequency="manual",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        # Manual mode - should never be due
        self.assertFalse(scheduler.should_generate_roadmap())

    def test_should_generate_roadmap_force(self):
        """Test forced generation."""
        scheduler = RoadmapScheduler(
            frequency="manual",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        # Force should work even in manual mode
        self.assertTrue(scheduler.should_generate_roadmap(force=True))

    def test_should_generate_roadmap_daily_not_due(self):
        """Test daily generation when not yet due."""
        scheduler = RoadmapScheduler(
            frequency="daily",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        # Mark as generated 1 hour ago
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        scheduler.state.last_generation_time = one_hour_ago

        # Should not be due yet (need 24 hours)
        self.assertFalse(scheduler.should_generate_roadmap())

    def test_should_generate_roadmap_daily_due(self):
        """Test daily generation when due."""
        scheduler = RoadmapScheduler(
            frequency="daily",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        # Mark as generated 25 hours ago
        twenty_five_hours_ago = datetime.now(timezone.utc) - timedelta(hours=25)
        scheduler.state.last_generation_time = twenty_five_hours_ago

        # Should be due (>24 hours elapsed)
        self.assertTrue(scheduler.should_generate_roadmap())

    def test_should_generate_roadmap_weekly_not_due(self):
        """Test weekly generation when not yet due."""
        scheduler = RoadmapScheduler(
            frequency="weekly",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        # Mark as generated 3 days ago
        three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
        scheduler.state.last_generation_time = three_days_ago

        # Should not be due yet (need 7 days)
        self.assertFalse(scheduler.should_generate_roadmap())

    def test_should_generate_roadmap_weekly_due(self):
        """Test weekly generation when due."""
        scheduler = RoadmapScheduler(
            frequency="weekly",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        # Mark as generated 8 days ago
        eight_days_ago = datetime.now(timezone.utc) - timedelta(days=8)
        scheduler.state.last_generation_time = eight_days_ago

        # Should be due (>7 days elapsed)
        self.assertTrue(scheduler.should_generate_roadmap())

    def test_mark_generation_complete(self):
        """Test marking generation as complete."""
        scheduler = RoadmapScheduler(
            frequency="daily",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        generation_time = datetime.now(timezone.utc)
        roadmap_id = "roadmap-20250110-120000"

        scheduler.mark_generation_complete(roadmap_id, generation_time)

        # Check state was updated
        self.assertEqual(scheduler.state.last_generation_time, generation_time)
        self.assertEqual(scheduler.state.last_roadmap_id, roadmap_id)
        self.assertEqual(scheduler.state.generation_count, 1)
        self.assertIsNone(scheduler.state.last_error)

        # Check next scheduled time was calculated
        expected_next = generation_time + timedelta(days=1)
        self.assertEqual(scheduler.state.next_scheduled_time, expected_next)

    def test_mark_generation_complete_increments_count(self):
        """Test that generation count increments."""
        scheduler = RoadmapScheduler(
            frequency="daily",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        # Generate multiple times
        for i in range(3):
            scheduler.mark_generation_complete(f"roadmap-{i}")

        self.assertEqual(scheduler.state.generation_count, 3)

    def test_mark_generation_complete_clears_error(self):
        """Test that successful generation clears errors."""
        scheduler = RoadmapScheduler(
            frequency="daily",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        # Mark as failed first
        scheduler.mark_generation_failed("Test error")
        self.assertIsNotNone(scheduler.state.last_error)

        # Then mark as complete
        scheduler.mark_generation_complete("roadmap-success")

        # Error should be cleared
        self.assertIsNone(scheduler.state.last_error)
        self.assertIsNone(scheduler.state.last_error_time)

    def test_mark_generation_failed(self):
        """Test marking generation as failed."""
        scheduler = RoadmapScheduler(
            frequency="daily",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        error_message = "Test error: generation failed"
        scheduler.mark_generation_failed(error_message)

        # Check error was recorded
        self.assertEqual(scheduler.state.last_error, error_message)
        self.assertIsNotNone(scheduler.state.last_error_time)

    def test_get_time_until_next_manual(self):
        """Test time until next for manual mode."""
        scheduler = RoadmapScheduler(
            frequency="manual",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        # Manual mode should return None
        self.assertIsNone(scheduler.get_time_until_next())

    def test_get_time_until_next_first_generation(self):
        """Test time until next for first generation."""
        scheduler = RoadmapScheduler(
            frequency="daily",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        # First generation should be due now (0 time)
        time_until = scheduler.get_time_until_next()
        self.assertEqual(time_until, timedelta(0))

    def test_get_time_until_next_after_generation(self):
        """Test time until next after generation."""
        scheduler = RoadmapScheduler(
            frequency="daily",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        # Generate 1 hour ago
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        scheduler.state.last_generation_time = one_hour_ago

        # Should have ~23 hours remaining
        time_until = scheduler.get_time_until_next()
        self.assertIsNotNone(time_until)
        # Allow some tolerance for test execution time
        self.assertGreater(time_until.total_seconds(), 22 * 3600)
        self.assertLess(time_until.total_seconds(), 24 * 3600)

    def test_get_next_scheduled_time_manual(self):
        """Test next scheduled time for manual mode."""
        scheduler = RoadmapScheduler(
            frequency="manual",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        self.assertIsNone(scheduler.get_next_scheduled_time())

    def test_get_next_scheduled_time_after_generation(self):
        """Test next scheduled time after generation."""
        scheduler = RoadmapScheduler(
            frequency="daily",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        generation_time = datetime.now(timezone.utc)
        scheduler.mark_generation_complete("roadmap-test", generation_time)

        next_time = scheduler.get_next_scheduled_time()
        expected = generation_time + timedelta(days=1)

        self.assertEqual(next_time, expected)

    def test_reset_schedule(self):
        """Test resetting schedule."""
        scheduler = RoadmapScheduler(
            frequency="daily",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        # Generate and then reset
        scheduler.mark_generation_complete("roadmap-test")
        self.assertEqual(scheduler.state.generation_count, 1)

        scheduler.reset_schedule()

        # State should be reset
        self.assertIsNone(scheduler.state.last_generation_time)
        self.assertIsNone(scheduler.state.last_roadmap_id)
        self.assertEqual(scheduler.state.generation_count, 0)

    def test_state_persistence(self):
        """Test that state is persisted and loaded."""
        # Create scheduler and mark generation
        scheduler1 = RoadmapScheduler(
            frequency="daily",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        generation_time = datetime.now(timezone.utc)
        roadmap_id = "roadmap-persist-test"
        scheduler1.mark_generation_complete(roadmap_id, generation_time)

        # Create new scheduler with same state file
        scheduler2 = RoadmapScheduler(
            frequency="daily",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        # State should be loaded
        self.assertEqual(scheduler2.state.last_roadmap_id, roadmap_id)
        self.assertEqual(scheduler2.state.generation_count, 1)
        # Times should match (allowing for microsecond precision in JSON)
        self.assertEqual(
            scheduler2.state.last_generation_time.replace(microsecond=0),
            generation_time.replace(microsecond=0),
        )

    def test_get_status(self):
        """Test getting schedule status."""
        scheduler = RoadmapScheduler(
            frequency="daily",
            logger=self.logger,
            state_file=str(self.state_file),
        )

        status = scheduler.get_status()

        # Check all expected fields
        self.assertIn("frequency", status)
        self.assertIn("last_generation_time", status)
        self.assertIn("last_roadmap_id", status)
        self.assertIn("generation_count", status)
        self.assertIn("next_scheduled_time", status)
        self.assertIn("time_until_next_seconds", status)
        self.assertIn("is_due", status)
        self.assertIn("last_error", status)

        # Check initial values
        self.assertEqual(status["frequency"], "daily")
        self.assertEqual(status["generation_count"], 0)
        self.assertTrue(status["is_due"])  # First generation

    def test_schedule_state_to_dict(self):
        """Test ScheduleState to_dict conversion."""
        state = ScheduleState(
            last_generation_time=datetime(2025, 1, 10, 12, 0, 0, tzinfo=timezone.utc),
            last_roadmap_id="roadmap-test",
            next_scheduled_time=datetime(2025, 1, 11, 12, 0, 0, tzinfo=timezone.utc),
            generation_count=5,
            last_error="Test error",
            last_error_time=datetime(2025, 1, 10, 11, 0, 0, tzinfo=timezone.utc),
        )

        result = state.to_dict()

        self.assertEqual(result["last_roadmap_id"], "roadmap-test")
        self.assertEqual(result["generation_count"], 5)
        self.assertEqual(result["last_error"], "Test error")
        self.assertIn("2025-01-10", result["last_generation_time"])

    def test_schedule_state_from_dict(self):
        """Test ScheduleState from_dict conversion."""
        data = {
            "last_generation_time": "2025-01-10T12:00:00+00:00",
            "last_roadmap_id": "roadmap-test",
            "next_scheduled_time": "2025-01-11T12:00:00+00:00",
            "generation_count": 5,
            "last_error": "Test error",
            "last_error_time": "2025-01-10T11:00:00+00:00",
        }

        state = ScheduleState.from_dict(data)

        self.assertEqual(state.last_roadmap_id, "roadmap-test")
        self.assertEqual(state.generation_count, 5)
        self.assertEqual(state.last_error, "Test error")
        self.assertIsNotNone(state.last_generation_time)

    def test_generation_frequency_enum(self):
        """Test GenerationFrequency enum values."""
        self.assertEqual(GenerationFrequency.MANUAL.value, "manual")
        self.assertEqual(GenerationFrequency.DAILY.value, "daily")
        self.assertEqual(GenerationFrequency.WEEKLY.value, "weekly")
        self.assertEqual(GenerationFrequency.MONTHLY.value, "monthly")


if __name__ == "__main__":
    unittest.main()
