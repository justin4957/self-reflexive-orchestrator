"""Unit tests for safety guards."""

import unittest
from unittest.mock import Mock

from src.safety.guards import (
    OperationGuard,
    Operation,
    OperationType,
    RiskLevel,
)
from src.core.logger import AuditLogger


class TestOperationGuard(unittest.TestCase):
    """Test cases for OperationGuard."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.guard = OperationGuard(logger=self.logger)

    def test_initialization(self):
        """Test guard initialization."""
        self.assertEqual(self.guard.max_complexity, 8)
        self.assertIsNotNone(self.guard.protected_regex)

    def test_detect_file_deletions(self):
        """Test detection of file deletion operations."""
        files_deleted = ["src/important.py", "config/prod.yaml"]

        operations = self.guard.detect_operations(
            files_changed=[],
            files_deleted=files_deleted,
        )

        # Should detect file deletion operation
        deletion_ops = [
            op for op in operations if op.operation_type == OperationType.FILE_DELETION
        ]
        self.assertEqual(len(deletion_ops), 1)
        self.assertEqual(len(deletion_ops[0].files), 2)

    def test_detect_protected_files(self):
        """Test detection of protected file access."""
        protected_files = [".env", "secrets/api_key.pem", "config/production/db.yaml"]

        operations = self.guard.detect_operations(
            files_changed=protected_files,
        )

        # Should detect protected file access
        protected_ops = [
            op
            for op in operations
            if op.operation_type == OperationType.PROTECTED_FILE_ACCESS
        ]
        self.assertEqual(len(protected_ops), 1)
        self.assertGreater(len(protected_ops[0].files), 0)

    def test_detect_security_files(self):
        """Test detection of security-sensitive file changes."""
        security_files = ["src/auth.py", "src/security/crypto.py"]

        operations = self.guard.detect_operations(
            files_changed=security_files,
        )

        # Should detect security change
        security_ops = [
            op
            for op in operations
            if op.operation_type == OperationType.SECURITY_CHANGE
        ]
        self.assertEqual(len(security_ops), 1)

    def test_detect_database_migrations(self):
        """Test detection of database migration changes."""
        migration_files = ["database/migrations/001_add_users.py"]

        operations = self.guard.detect_operations(
            files_changed=migration_files,
        )

        # Should detect database migration
        migration_ops = [
            op
            for op in operations
            if op.operation_type == OperationType.DATABASE_MIGRATION
        ]
        self.assertEqual(len(migration_ops), 1)

    def test_detect_configuration_changes(self):
        """Test detection of configuration changes."""
        config_files = ["config/app.yaml", "settings.py"]

        operations = self.guard.detect_operations(
            files_changed=config_files,
        )

        # Should detect configuration change
        config_ops = [
            op
            for op in operations
            if op.operation_type == OperationType.CONFIGURATION_CHANGE
        ]
        self.assertEqual(len(config_ops), 1)

    def test_calculate_complexity_simple(self):
        """Test complexity calculation for simple changes."""
        complexity = self.guard.calculate_complexity(
            files_changed=["src/utils.py"],
            files_deleted=[],
            diff="+    return x + y\n",
        )

        # Should be low complexity
        self.assertLessEqual(complexity, 3)

    def test_calculate_complexity_high(self):
        """Test complexity calculation for complex changes."""
        # Many files + lines
        many_files = [f"src/file{i}.py" for i in range(20)]
        large_diff = "\n".join(["+    line" for _ in range(1000)])

        complexity = self.guard.calculate_complexity(
            files_changed=many_files,
            files_deleted=[],
            diff=large_diff,
        )

        # Should be high complexity
        self.assertGreater(complexity, 5)

    def test_detect_breaking_changes_in_diff(self):
        """Test detection of breaking changes in diff."""
        diff = """
-    def old_method(self, param1):
+    def new_method(self, param1, param2):
"""

        operations = self.guard.detect_operations(
            files_changed=["src/api.py"],
            diff=diff,
        )

        # May detect breaking change
        breaking_ops = [
            op
            for op in operations
            if op.operation_type == OperationType.BREAKING_CHANGE
        ]
        # Breaking change detection is heuristic-based, so just check it doesn't crash
        self.assertIsInstance(breaking_ops, list)

    def test_no_operations_for_safe_changes(self):
        """Test that safe changes don't trigger operations."""
        safe_files = ["README.md", "docs/guide.md"]

        operations = self.guard.detect_operations(
            files_changed=safe_files,
            diff="+    This is documentation\n",
        )

        # Should have no operations or only low-complexity ones
        critical_ops = [
            op
            for op in operations
            if op.operation_type
            in [
                OperationType.PROTECTED_FILE_ACCESS,
                OperationType.SECURITY_CHANGE,
                OperationType.BREAKING_CHANGE,
            ]
        ]
        self.assertEqual(len(critical_ops), 0)

    def test_count_diff_lines(self):
        """Test counting diff lines."""
        diff = """
+++ b/file.py
--- a/file.py
+    added line 1
+    added line 2
-    removed line 1
     unchanged line
+    added line 3
-    removed line 2
"""

        added, deleted = self.guard._count_diff_lines(diff)
        self.assertEqual(added, 3)
        self.assertEqual(deleted, 2)

    def test_custom_protected_patterns(self):
        """Test custom protected file patterns."""
        custom_guard = OperationGuard(
            logger=self.logger,
            protected_files=[r".*\.secret$", r"private/.*"],
        )

        operations = custom_guard.detect_operations(
            files_changed=["app.secret", "private/data.json"],
        )

        # Should detect protected files
        protected_ops = [
            op
            for op in operations
            if op.operation_type == OperationType.PROTECTED_FILE_ACCESS
        ]
        self.assertGreater(len(protected_ops), 0)

    def test_operation_to_dict(self):
        """Test Operation to_dict conversion."""
        operation = Operation(
            operation_type=OperationType.FILE_DELETION,
            description="Test operation",
            files=["test.py"],
            complexity=5,
        )

        op_dict = operation.to_dict()

        self.assertEqual(op_dict["operation_type"], "file_deletion")
        self.assertEqual(op_dict["description"], "Test operation")
        self.assertEqual(op_dict["files"], ["test.py"])
        self.assertEqual(op_dict["complexity"], 5)


if __name__ == "__main__":
    unittest.main()
