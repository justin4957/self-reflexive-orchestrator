"""State management for the orchestrator."""

import json
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict, field


class OrchestratorState(Enum):
    """States of the orchestrator."""

    IDLE = "idle"
    MONITORING = "monitoring"
    ANALYZING_ISSUE = "analyzing_issue"
    IMPLEMENTING = "implementing"
    TESTING = "testing"
    CREATING_PR = "creating_pr"
    REVIEWING = "reviewing"
    WAITING_FOR_CI = "waiting_for_ci"
    MERGING = "merging"
    GENERATING_ROADMAP = "generating_roadmap"
    VALIDATING_ROADMAP = "validating_roadmap"
    CREATING_ISSUES = "creating_issues"
    ERROR = "error"
    WAITING_FOR_APPROVAL = "waiting_for_approval"


@dataclass
class WorkItem:
    """Represents a work item being processed."""

    item_type: str  # "issue", "pr", "roadmap"
    item_id: str
    state: str
    created_at: str
    updated_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkItem":
        """Create from dictionary."""
        return cls(**data)


class StateManager:
    """Manages orchestrator state and work items."""

    def __init__(self, storage_backend: Optional[Any] = None):
        """Initialize state manager.

        Args:
            storage_backend: Optional storage backend (Redis, SQLite, etc.)
        """
        self.storage = storage_backend
        self.current_state = OrchestratorState.IDLE
        self.work_items: Dict[str, WorkItem] = {}
        self.state_history: list = []

    def transition_to(self, new_state: OrchestratorState, reason: Optional[str] = None):
        """Transition to a new state.

        Args:
            new_state: Target state
            reason: Reason for transition
        """
        old_state = self.current_state
        self.current_state = new_state

        # Record transition in history
        self.state_history.append(
            {
                "from": old_state.value,
                "to": new_state.value,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": reason,
            }
        )

        # Persist if storage available
        if self.storage:
            self._persist_state()

    def get_current_state(self) -> OrchestratorState:
        """Get current state."""
        return self.current_state

    def add_work_item(
        self,
        item_type: str,
        item_id: str,
        initial_state: str = "pending",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WorkItem:
        """Add a new work item.

        Args:
            item_type: Type of work item (issue, pr, roadmap)
            item_id: Unique identifier
            initial_state: Initial state
            metadata: Additional metadata

        Returns:
            Created WorkItem
        """
        now = datetime.utcnow().isoformat()
        work_item = WorkItem(
            item_type=item_type,
            item_id=item_id,
            state=initial_state,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

        self.work_items[f"{item_type}:{item_id}"] = work_item

        if self.storage:
            self._persist_work_item(work_item)

        return work_item

    def get_work_item(self, item_type: str, item_id: str) -> Optional[WorkItem]:
        """Get a work item.

        Args:
            item_type: Type of work item
            item_id: Item identifier

        Returns:
            WorkItem if found, None otherwise
        """
        key = f"{item_type}:{item_id}"
        return self.work_items.get(key)

    def update_work_item(
        self,
        item_type: str,
        item_id: str,
        state: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        increment_retry: bool = False,
    ):
        """Update a work item.

        Args:
            item_type: Type of work item
            item_id: Item identifier
            state: New state
            metadata: Metadata to merge
            error: Error message
            increment_retry: Whether to increment retry count
        """
        work_item = self.get_work_item(item_type, item_id)
        if not work_item:
            raise ValueError(f"Work item not found: {item_type}:{item_id}")

        if state:
            work_item.state = state

        if metadata:
            work_item.metadata.update(metadata)

        if error:
            work_item.error = error

        if increment_retry:
            work_item.retry_count += 1

        work_item.updated_at = datetime.utcnow().isoformat()

        if self.storage:
            self._persist_work_item(work_item)

    def remove_work_item(self, item_type: str, item_id: str):
        """Remove a work item.

        Args:
            item_type: Type of work item
            item_id: Item identifier
        """
        key = f"{item_type}:{item_id}"
        if key in self.work_items:
            del self.work_items[key]

            if self.storage:
                self._delete_work_item(item_type, item_id)

    def get_pending_work_items(self, item_type: Optional[str] = None) -> list[WorkItem]:
        """Get all pending work items.

        Args:
            item_type: Optional filter by type

        Returns:
            List of pending work items
        """
        items = self.work_items.values()

        if item_type:
            items = [item for item in items if item.item_type == item_type]

        return [item for item in items if item.state == "pending"]

    def get_in_progress_work_items(
        self, item_type: Optional[str] = None
    ) -> list[WorkItem]:
        """Get all in-progress work items.

        Args:
            item_type: Optional filter by type

        Returns:
            List of in-progress work items
        """
        items = self.work_items.values()

        if item_type:
            items = [item for item in items if item.item_type == item_type]

        return [item for item in items if item.state == "in_progress"]

    def get_state_summary(self) -> Dict[str, Any]:
        """Get summary of current state.

        Returns:
            Dictionary with state summary
        """
        return {
            "current_state": self.current_state.value,
            "work_items": {
                "total": len(self.work_items),
                "pending": len(
                    [i for i in self.work_items.values() if i.state == "pending"]
                ),
                "in_progress": len(
                    [i for i in self.work_items.values() if i.state == "in_progress"]
                ),
                "completed": len(
                    [i for i in self.work_items.values() if i.state == "completed"]
                ),
                "failed": len(
                    [i for i in self.work_items.values() if i.state == "failed"]
                ),
            },
            "last_transition": self.state_history[-1] if self.state_history else None,
        }

    def _persist_state(self):
        """Persist current state to storage."""
        if not self.storage:
            return

        # Implementation depends on storage backend
        # For Redis: self.storage.set("orchestrator:state", self.current_state.value)
        # For SQLite: self.storage.execute("UPDATE state SET ...")
        pass

    def _persist_work_item(self, work_item: WorkItem):
        """Persist work item to storage."""
        if not self.storage:
            return

        # Implementation depends on storage backend
        # For Redis: self.storage.hset(f"work_item:{work_item.item_type}:{work_item.item_id}", mapping=work_item.to_dict())
        pass

    def _delete_work_item(self, item_type: str, item_id: str):
        """Delete work item from storage."""
        if not self.storage:
            return

        # Implementation depends on storage backend
        # For Redis: self.storage.delete(f"work_item:{item_type}:{item_id}")
        pass

    def load_from_storage(self):
        """Load state from storage."""
        if not self.storage:
            return

        # Implementation depends on storage backend
        # Load current state, work items, and history
        pass

    def clear_history(self):
        """Clear state history."""
        self.state_history.clear()

    def export_state(self) -> str:
        """Export current state as JSON.

        Returns:
            JSON string of current state
        """
        return json.dumps(
            {
                "current_state": self.current_state.value,
                "work_items": {k: v.to_dict() for k, v in self.work_items.items()},
                "state_history": self.state_history,
            },
            indent=2,
        )

    def import_state(self, state_json: str):
        """Import state from JSON.

        Args:
            state_json: JSON string of state to import
        """
        data = json.loads(state_json)

        self.current_state = OrchestratorState(data["current_state"])
        self.work_items = {
            k: WorkItem.from_dict(v) for k, v in data.get("work_items", {}).items()
        }
        self.state_history = data.get("state_history", [])
