"""Safety guards for detecting and preventing dangerous operations.

Implements operation detection and classification for:
- File deletions and modifications
- Security-sensitive file changes
- Breaking API changes
- High-complexity operations
- Protected file access
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ..core.logger import AuditLogger


class RiskLevel(Enum):
    """Risk levels for operations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class OperationType(Enum):
    """Types of operations that require safety validation."""

    FILE_DELETION = "file_deletion"
    FILE_MODIFICATION = "file_modification"
    SECURITY_CHANGE = "security_change"
    BREAKING_CHANGE = "breaking_change"
    COMPLEX_CHANGE = "complex_change"
    PROTECTED_FILE_ACCESS = "protected_file_access"
    DATABASE_MIGRATION = "database_migration"
    CONFIGURATION_CHANGE = "configuration_change"


@dataclass
class Operation:
    """Represents an operation requiring safety validation."""

    operation_type: OperationType
    description: str
    files: List[str] = field(default_factory=list)
    changes_summary: str = ""
    complexity: int = 0  # 0-10 scale
    scope: str = ""  # Brief description of impact scope
    justification: str = ""  # Why this operation is needed
    detected_at: Optional[str] = None
    additional_context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "operation_type": self.operation_type.value,
            "description": self.description,
            "files": self.files,
            "changes_summary": self.changes_summary,
            "complexity": self.complexity,
            "scope": self.scope,
            "justification": self.justification,
            "detected_at": self.detected_at,
            "additional_context": self.additional_context,
        }


@dataclass
class GuardDecision:
    """Decision made by safety guards."""

    allowed: bool
    risk_level: RiskLevel
    operation: Operation
    rationale: str
    requires_approval: bool = False
    blocking_reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "allowed": self.allowed,
            "risk_level": self.risk_level.value,
            "operation": self.operation.to_dict(),
            "rationale": self.rationale,
            "requires_approval": self.requires_approval,
            "blocking_reasons": self.blocking_reasons,
            "warnings": self.warnings,
            "recommendations": self.recommendations,
        }


class OperationGuard:
    """Detects and classifies operations requiring safety validation.

    Responsibilities:
    - Detect file deletions and modifications
    - Identify security-sensitive changes
    - Track breaking API changes
    - Calculate operation complexity
    - Monitor protected file access
    """

    # Protected file patterns
    PROTECTED_PATTERNS = [
        r"\.env$",
        r"\.env\..*",
        r".*\.key$",
        r".*\.pem$",
        r".*\.p12$",
        r".*\.pfx$",
        r"config/production/.*",
        r"secrets/.*",
        r".*credentials.*",
        r".*password.*\.json$",
        r".*\.secret$",
    ]

    # Security-sensitive file patterns
    SECURITY_SENSITIVE_PATTERNS = [
        r".*auth.*\.py$",
        r".*security.*\.py$",
        r".*permission.*\.py$",
        r".*crypto.*\.py$",
        r".*token.*\.py$",
        r".*session.*\.py$",
    ]

    # Database migration patterns
    DATABASE_MIGRATION_PATTERNS = [
        r"database/migrations/.*",
        r".*migrations/.*\.py$",
        r".*alembic/.*",
        r".*flyway/.*",
    ]

    # Configuration file patterns
    CONFIG_PATTERNS = [
        r".*config.*\.yaml$",
        r".*config.*\.yml$",
        r".*config.*\.json$",
        r".*\.toml$",
        r".*settings.*\.py$",
    ]

    # Complexity thresholds
    MAX_COMPLEXITY = 8  # 0-10 scale
    COMPLEXITY_FACTORS = {
        "files_changed": 0.5,  # Per file
        "lines_added": 0.001,  # Per line
        "lines_deleted": 0.001,  # Per line
        "critical_files": 2.0,  # Per critical file
        "dependencies": 1.0,  # Per new dependency
    }

    def __init__(
        self,
        logger: AuditLogger,
        protected_files: Optional[List[str]] = None,
        max_complexity: int = MAX_COMPLEXITY,
    ):
        """Initialize operation guard.

        Args:
            logger: Audit logger
            protected_files: Additional protected file patterns
            max_complexity: Maximum allowed complexity (0-10)
        """
        self.logger = logger
        self.max_complexity = max_complexity

        # Combine default and custom protected patterns
        self.protected_patterns = self.PROTECTED_PATTERNS.copy()
        if protected_files:
            self.protected_patterns.extend(protected_files)

        # Compile regex patterns
        self.protected_regex = [re.compile(p) for p in self.protected_patterns]
        self.security_regex = [re.compile(p) for p in self.SECURITY_SENSITIVE_PATTERNS]
        self.migration_regex = [re.compile(p) for p in self.DATABASE_MIGRATION_PATTERNS]
        self.config_regex = [re.compile(p) for p in self.CONFIG_PATTERNS]

        self.logger.info(
            "operation_guard_initialized",
            protected_patterns_count=len(self.protected_patterns),
            max_complexity=max_complexity,
        )

    def detect_operations(
        self,
        files_changed: List[str],
        files_deleted: List[str] = None,
        diff: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Operation]:
        """Detect operations requiring safety validation.

        Args:
            files_changed: List of files being changed
            files_deleted: List of files being deleted
            diff: Git diff of changes
            context: Additional context about the operation

        Returns:
            List of detected operations
        """
        operations = []
        files_deleted = files_deleted or []
        context = context or {}

        # Detect file deletions
        if files_deleted:
            operations.append(
                Operation(
                    operation_type=OperationType.FILE_DELETION,
                    description=f"Deleting {len(files_deleted)} file(s)",
                    files=files_deleted,
                    changes_summary=f"Files to delete: {', '.join(files_deleted[:5])}{'...' if len(files_deleted) > 5 else ''}",
                    scope=f"{len(files_deleted)} files",
                    additional_context=context,
                )
            )

        # Check for protected file access
        protected_files = self._find_protected_files(files_changed + files_deleted)
        if protected_files:
            operations.append(
                Operation(
                    operation_type=OperationType.PROTECTED_FILE_ACCESS,
                    description=f"Accessing {len(protected_files)} protected file(s)",
                    files=protected_files,
                    changes_summary=f"Protected files: {', '.join(protected_files)}",
                    scope=f"{len(protected_files)} protected files",
                    additional_context=context,
                )
            )

        # Check for security-sensitive changes
        security_files = self._find_security_files(files_changed)
        if security_files:
            operations.append(
                Operation(
                    operation_type=OperationType.SECURITY_CHANGE,
                    description=f"Modifying {len(security_files)} security-sensitive file(s)",
                    files=security_files,
                    changes_summary=f"Security files: {', '.join(security_files)}",
                    scope=f"{len(security_files)} security files",
                    additional_context=context,
                )
            )

        # Check for database migrations
        migration_files = self._find_migration_files(files_changed)
        if migration_files:
            operations.append(
                Operation(
                    operation_type=OperationType.DATABASE_MIGRATION,
                    description=f"Database migration affecting {len(migration_files)} file(s)",
                    files=migration_files,
                    changes_summary=f"Migration files: {', '.join(migration_files)}",
                    scope="Database schema",
                    additional_context=context,
                )
            )

        # Check for configuration changes
        config_files = self._find_config_files(files_changed)
        if config_files:
            operations.append(
                Operation(
                    operation_type=OperationType.CONFIGURATION_CHANGE,
                    description=f"Configuration change in {len(config_files)} file(s)",
                    files=config_files,
                    changes_summary=f"Config files: {', '.join(config_files)}",
                    scope="Application configuration",
                    additional_context=context,
                )
            )

        # Calculate complexity
        complexity = self.calculate_complexity(
            files_changed=files_changed,
            files_deleted=files_deleted,
            diff=diff,
        )

        if complexity > self.max_complexity:
            operations.append(
                Operation(
                    operation_type=OperationType.COMPLEX_CHANGE,
                    description=f"High complexity change (score: {complexity}/{self.max_complexity})",
                    files=files_changed + files_deleted,
                    changes_summary=f"{len(files_changed)} files changed, {len(files_deleted)} deleted",
                    complexity=complexity,
                    scope=f"{len(files_changed) + len(files_deleted)} files total",
                    additional_context=context,
                )
            )

        # Detect breaking changes from diff
        if diff and self._has_breaking_changes(diff):
            operations.append(
                Operation(
                    operation_type=OperationType.BREAKING_CHANGE,
                    description="Potential breaking API changes detected",
                    files=files_changed,
                    changes_summary="Breaking changes detected in diff",
                    scope="API consumers",
                    additional_context=context,
                )
            )

        self.logger.info(
            "operations_detected",
            operation_count=len(operations),
            operation_types=[op.operation_type.value for op in operations],
        )

        return operations

    def calculate_complexity(
        self,
        files_changed: List[str],
        files_deleted: List[str],
        diff: str,
    ) -> int:
        """Calculate operation complexity score (0-10).

        Args:
            files_changed: Files being changed
            files_deleted: Files being deleted
            diff: Git diff

        Returns:
            Complexity score (0-10)
        """
        score = 0.0

        # Factor: Number of files
        score += len(files_changed) * self.COMPLEXITY_FACTORS["files_changed"]
        score += len(files_deleted) * self.COMPLEXITY_FACTORS["files_changed"]

        # Factor: Lines changed (from diff)
        lines_added, lines_deleted = self._count_diff_lines(diff)
        score += lines_added * self.COMPLEXITY_FACTORS["lines_added"]
        score += lines_deleted * self.COMPLEXITY_FACTORS["lines_deleted"]

        # Factor: Critical files
        critical_files = (
            self._find_protected_files(files_changed)
            + self._find_security_files(files_changed)
            + self._find_migration_files(files_changed)
        )
        score += len(set(critical_files)) * self.COMPLEXITY_FACTORS["critical_files"]

        # Cap at 10
        return min(int(score), 10)

    def _find_protected_files(self, files: List[str]) -> List[str]:
        """Find protected files in list."""
        protected = []
        for file_path in files:
            if any(regex.search(file_path) for regex in self.protected_regex):
                protected.append(file_path)
        return protected

    def _find_security_files(self, files: List[str]) -> List[str]:
        """Find security-sensitive files in list."""
        security = []
        for file_path in files:
            if any(regex.search(file_path) for regex in self.security_regex):
                security.append(file_path)
        return security

    def _find_migration_files(self, files: List[str]) -> List[str]:
        """Find database migration files in list."""
        migrations = []
        for file_path in files:
            if any(regex.search(file_path) for regex in self.migration_regex):
                migrations.append(file_path)
        return migrations

    def _find_config_files(self, files: List[str]) -> List[str]:
        """Find configuration files in list."""
        configs = []
        for file_path in files:
            if any(regex.search(file_path) for regex in self.config_regex):
                configs.append(file_path)
        return configs

    def _count_diff_lines(self, diff: str) -> tuple:
        """Count lines added and deleted from diff.

        Returns:
            Tuple of (lines_added, lines_deleted)
        """
        lines_added = 0
        lines_deleted = 0

        for line in diff.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                lines_added += 1
            elif line.startswith("-") and not line.startswith("---"):
                lines_deleted += 1

        return lines_added, lines_deleted

    def _has_breaking_changes(self, diff: str) -> bool:
        """Detect potential breaking changes in diff.

        Simple heuristic detection for:
        - Function/method signature changes
        - Removed public methods
        - Changed return types
        """
        breaking_patterns = [
            r"-\s*def\s+\w+\(",  # Removed function
            r"-\s*class\s+\w+",  # Removed class
            r"-\s*async\s+def\s+\w+\(",  # Removed async function
            r"def\s+\w+\([^)]*\):.*->.*\n.*\+.*def\s+\w+\([^)]*\):.*->",  # Changed return type
        ]

        for pattern in breaking_patterns:
            if re.search(pattern, diff, re.MULTILINE):
                return True

        return False
