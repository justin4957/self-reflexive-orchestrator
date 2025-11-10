"""Unit tests for RoadmapCycle."""

import unittest
from unittest.mock import Mock, MagicMock
from datetime import datetime, timezone
from pathlib import Path

from src.cycles.roadmap_cycle import RoadmapCycle, RoadmapCycleResult
from src.cycles.roadmap_generator import GeneratedRoadmap, RoadmapMetadata
from src.cycles.roadmap_validator import ValidatedRoadmap, DialecticalValidation
from src.cycles.issue_creator import IssueCreationResult
from src.cycles.multi_agent_ideation import (
    IdeationResult,
    SynthesizedRoadmap,
)
from src.integrations.github_client import GitHubClient
from src.integrations.multi_agent_coder_client import MultiAgentCoderClient
from src.core.logger import AuditLogger


class TestRoadmapCycle(unittest.TestCase):
    """Test cases for RoadmapCycle."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.github_client = Mock(spec=GitHubClient)
        self.multi_agent_client = Mock(spec=MultiAgentCoderClient)

        # Use current directory (which exists) for testing
        self.cycle = RoadmapCycle(
            repository_path=str(Path.cwd()),
            github_client=self.github_client,
            multi_agent_client=self.multi_agent_client,
            logger=self.logger,
            scheduler_frequency="manual",
            auto_create_issues=True,
            min_validation_confidence=0.8,
        )

    def test_initialization(self):
        """Test roadmap cycle initialization."""
        self.assertEqual(self.cycle.repository_path, Path.cwd())
        self.assertEqual(self.cycle.github_client, self.github_client)
        self.assertEqual(self.cycle.multi_agent_client, self.multi_agent_client)
        self.assertTrue(self.cycle.auto_create_issues)
        self.assertEqual(self.cycle.min_validation_confidence, 0.8)

        # Components should be initialized
        self.assertIsNotNone(self.cycle.roadmap_generator)
        self.assertIsNotNone(self.cycle.roadmap_validator)
        self.assertIsNotNone(self.cycle.roadmap_scheduler)
        self.assertIsNotNone(self.cycle.issue_creator)

    def test_should_run_cycle_force(self):
        """Test that force flag works."""
        # Should return True when forced
        self.assertTrue(self.cycle.should_run_cycle(force=True))

    def test_should_run_cycle_manual_mode(self):
        """Test that manual mode doesn't auto-run."""
        # Manual mode should not auto-run
        self.assertFalse(self.cycle.should_run_cycle(force=False))

    def test_get_schedule_status(self):
        """Test getting schedule status."""
        status = self.cycle.get_schedule_status()

        # Should return status dictionary
        self.assertIn("frequency", status)
        self.assertIn("last_generation_time", status)
        self.assertIn("generation_count", status)
        self.assertEqual(status["frequency"], "manual")

    def test_reset_schedule(self):
        """Test resetting schedule."""
        # Should not raise exception
        self.cycle.reset_schedule()

        # Logger should be called
        self.logger.info.assert_called()

    def test_roadmap_cycle_result_to_dict(self):
        """Test RoadmapCycleResult to_dict conversion."""
        # Create mock objects
        mock_roadmap = Mock(spec=GeneratedRoadmap)
        mock_roadmap.to_dict.return_value = {"test": "roadmap"}

        mock_validated = Mock(spec=ValidatedRoadmap)
        mock_validated.to_dict.return_value = {"test": "validated"}

        mock_issues = Mock(spec=IssueCreationResult)
        mock_issues.to_dict.return_value = {"test": "issues"}

        result = RoadmapCycleResult(
            cycle_id="test-cycle",
            started_at=datetime(2025, 1, 10, 12, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2025, 1, 10, 12, 5, 0, tzinfo=timezone.utc),
            duration_seconds=300.0,
            roadmap=mock_roadmap,
            validated_roadmap=mock_validated,
            issue_creation=mock_issues,
            total_cost=0.75,
            total_tokens=8000,
            proposals_generated=20,
            proposals_validated=20,
            proposals_approved=12,
            proposals_rejected=3,
            issues_created=12,
        )

        result_dict = result.to_dict()

        # Check all fields
        self.assertEqual(result_dict["cycle_id"], "test-cycle")
        self.assertEqual(result_dict["duration_seconds"], 300.0)
        self.assertEqual(result_dict["total_cost"], 0.75)
        self.assertEqual(result_dict["total_tokens"], 8000)
        self.assertEqual(result_dict["proposals_generated"], 20)
        self.assertEqual(result_dict["proposals_approved"], 12)
        self.assertEqual(result_dict["proposals_rejected"], 3)
        self.assertEqual(result_dict["issues_created"], 12)


if __name__ == "__main__":
    unittest.main()
