"""Tests for state management."""

import pytest
from datetime import datetime

from src.core.state import (
    StateManager,
    OrchestratorState,
    WorkItem,
)


class TestWorkItem:
    """Test WorkItem dataclass."""

    def test_work_item_creation(self):
        """Test creating a work item."""
        item = WorkItem(
            item_type="issue",
            item_id="123",
            state="pending",
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        )

        assert item.item_type == "issue"
        assert item.item_id == "123"
        assert item.state == "pending"
        assert item.retry_count == 0

    def test_work_item_to_dict(self):
        """Test converting work item to dictionary."""
        item = WorkItem(
            item_type="issue",
            item_id="123",
            state="pending",
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
            metadata={"title": "Test Issue"},
        )

        data = item.to_dict()
        assert data["item_type"] == "issue"
        assert data["item_id"] == "123"
        assert data["metadata"]["title"] == "Test Issue"

    def test_work_item_from_dict(self):
        """Test creating work item from dictionary."""
        data = {
            "item_type": "pr",
            "item_id": "456",
            "state": "in_progress",
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
            "metadata": {"branch": "feature/test"},
            "error": None,
            "retry_count": 1,
        }

        item = WorkItem.from_dict(data)
        assert item.item_type == "pr"
        assert item.item_id == "456"
        assert item.state == "in_progress"
        assert item.retry_count == 1


class TestStateManager:
    """Test state manager."""

    def test_initial_state(self):
        """Test initial state is IDLE."""
        manager = StateManager()
        assert manager.get_current_state() == OrchestratorState.IDLE

    def test_state_transition(self):
        """Test state transitions."""
        manager = StateManager()
        manager.transition_to(OrchestratorState.MONITORING, "Starting monitor")

        assert manager.get_current_state() == OrchestratorState.MONITORING
        assert len(manager.state_history) == 1
        assert manager.state_history[0]["from"] == "idle"
        assert manager.state_history[0]["to"] == "monitoring"
        assert manager.state_history[0]["reason"] == "Starting monitor"

    def test_add_work_item(self):
        """Test adding a work item."""
        manager = StateManager()
        item = manager.add_work_item(
            "issue",
            "123",
            metadata={"title": "Test Issue"},
        )

        assert item.item_type == "issue"
        assert item.item_id == "123"
        assert item.state == "pending"
        assert item.metadata["title"] == "Test Issue"

    def test_get_work_item(self):
        """Test getting a work item."""
        manager = StateManager()
        manager.add_work_item("issue", "123")

        item = manager.get_work_item("issue", "123")
        assert item is not None
        assert item.item_id == "123"

    def test_get_nonexistent_work_item(self):
        """Test getting a nonexistent work item returns None."""
        manager = StateManager()
        item = manager.get_work_item("issue", "999")
        assert item is None

    def test_update_work_item(self):
        """Test updating a work item."""
        manager = StateManager()
        manager.add_work_item("issue", "123")

        manager.update_work_item(
            "issue",
            "123",
            state="in_progress",
            metadata={"step": "implementation"},
        )

        item = manager.get_work_item("issue", "123")
        assert item.state == "in_progress"
        assert item.metadata["step"] == "implementation"

    def test_update_work_item_increment_retry(self):
        """Test incrementing retry count."""
        manager = StateManager()
        manager.add_work_item("issue", "123")

        manager.update_work_item("issue", "123", increment_retry=True)
        manager.update_work_item("issue", "123", increment_retry=True)

        item = manager.get_work_item("issue", "123")
        assert item.retry_count == 2

    def test_remove_work_item(self):
        """Test removing a work item."""
        manager = StateManager()
        manager.add_work_item("issue", "123")

        manager.remove_work_item("issue", "123")

        item = manager.get_work_item("issue", "123")
        assert item is None

    def test_get_pending_work_items(self):
        """Test getting pending work items."""
        manager = StateManager()
        manager.add_work_item("issue", "1", initial_state="pending")
        manager.add_work_item("issue", "2", initial_state="in_progress")
        manager.add_work_item("issue", "3", initial_state="pending")
        manager.add_work_item("pr", "4", initial_state="pending")

        pending = manager.get_pending_work_items()
        assert len(pending) == 3

        pending_issues = manager.get_pending_work_items("issue")
        assert len(pending_issues) == 2

    def test_get_in_progress_work_items(self):
        """Test getting in-progress work items."""
        manager = StateManager()
        manager.add_work_item("issue", "1", initial_state="pending")
        manager.add_work_item("issue", "2", initial_state="in_progress")
        manager.add_work_item("issue", "3", initial_state="in_progress")

        in_progress = manager.get_in_progress_work_items()
        assert len(in_progress) == 2

    def test_get_state_summary(self):
        """Test getting state summary."""
        manager = StateManager()
        manager.add_work_item("issue", "1", initial_state="pending")
        manager.add_work_item("issue", "2", initial_state="in_progress")
        manager.add_work_item("issue", "3", initial_state="completed")
        manager.add_work_item("issue", "4", initial_state="failed")

        summary = manager.get_state_summary()
        assert summary["current_state"] == "idle"
        assert summary["work_items"]["total"] == 4
        assert summary["work_items"]["pending"] == 1
        assert summary["work_items"]["in_progress"] == 1
        assert summary["work_items"]["completed"] == 1
        assert summary["work_items"]["failed"] == 1

    def test_export_import_state(self):
        """Test exporting and importing state."""
        manager = StateManager()
        manager.transition_to(OrchestratorState.MONITORING)
        manager.add_work_item("issue", "123", metadata={"title": "Test"})

        # Export state
        state_json = manager.export_state()

        # Create new manager and import
        new_manager = StateManager()
        new_manager.import_state(state_json)

        assert new_manager.get_current_state() == OrchestratorState.MONITORING
        assert new_manager.get_work_item("issue", "123") is not None
        assert new_manager.get_work_item("issue", "123").metadata["title"] == "Test"
