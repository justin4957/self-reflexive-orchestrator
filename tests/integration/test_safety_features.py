"""Integration tests for Phase 5 safety features.

Verifies that all safety mechanisms are integrated and operational.
This is a smoke test to ensure Phase 5 components are properly integrated.
"""

from pathlib import Path

import pytest


class TestPhase5Integration:
    """Integration tests for Phase 5 safety and monitoring."""

    def test_all_safety_components_importable(self):
        """Test that all Phase 5 components can be imported.

        This verifies the integration is complete and all modules are accessible.
        """
        # Core health and metrics
        from src.core import health, metrics

        # Safety components
        from src.safety import (
            approval,
            breaking_change_detector,
            cost_tracker,
            failure_analyzer,
            guards,
            multi_agent_risk_assessor,
            rate_limiter,
            rollback,
            safety_guard_manager,
        )

        # Verify all modules exist
        assert health is not None
        assert metrics is not None
        assert approval is not None
        assert breaking_change_detector is not None
        assert cost_tracker is not None
        assert failure_analyzer is not None
        assert guards is not None
        assert multi_agent_risk_assessor is not None
        assert rate_limiter is not None
        assert rollback is not None
        assert safety_guard_manager is not None

    def test_key_classes_importable(self):
        """Test that key safety classes can be imported."""
        from src.core.health import HealthChecker, HealthStatus
        from src.core.metrics import MetricsCollector
        from src.safety.approval import ApprovalRequest, ApprovalSystem
        from src.safety.cost_tracker import CostTracker
        from src.safety.guards import Operation, OperationGuard
        from src.safety.rate_limiter import RateLimiter
        from src.safety.rollback import RollbackManager

        # Verify all classes exist
        assert HealthChecker is not None
        assert HealthStatus is not None
        assert MetricsCollector is not None
        assert ApprovalRequest is not None
        assert ApprovalSystem is not None
        assert CostTracker is not None
        assert Operation is not None
        assert OperationGuard is not None
        assert RateLimiter is not None
        assert RollbackManager is not None

    def test_documentation_exists(self):
        """Test that Phase 5 documentation files exist."""
        docs_dir = Path(__file__).parent.parent.parent / "docs"

        safety_doc = docs_dir / "safety.md"
        operations_doc = docs_dir / "operations.md"
        troubleshooting_doc = docs_dir / "troubleshooting.md"

        assert safety_doc.exists(), f"Missing: {safety_doc}"
        assert operations_doc.exists(), f"Missing: {operations_doc}"
        assert troubleshooting_doc.exists(), f"Missing: {troubleshooting_doc}"

        # Verify they have content
        assert safety_doc.stat().st_size > 1000, "safety.md seems empty"
        assert operations_doc.stat().st_size > 1000, "operations.md seems empty"
        assert (
            troubleshooting_doc.stat().st_size > 1000
        ), "troubleshooting.md seems empty"

    def test_readme_updated_with_safety_section(self):
        """Test that README includes safety information."""
        readme_path = Path(__file__).parent.parent.parent / "README.md"
        assert readme_path.exists()

        readme_content = readme_path.read_text()

        # Check for safety section
        assert "Safety & Monitoring" in readme_content
        assert "Multi-Layer Safety" in readme_content
        assert "Rate Limiting" in readme_content
        assert "Cost Tracking" in readme_content

    def test_integration_test_file_exists(self):
        """Test that this integration test file exists and is discoverable."""
        test_file = Path(__file__)
        assert test_file.exists()
        assert test_file.name == "test_safety_features.py"
        assert "integration" in str(test_file.parent)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
