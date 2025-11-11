"""Codebase analyzer for understanding project structure and metrics.

Analyzes repository structure, dependencies, code metrics, and patterns
to provide comprehensive insights for roadmap generation.
"""

import ast
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ..core.logger import AuditLogger


@dataclass
class FileMetrics:
    """Metrics for a single file."""

    path: str
    language: str
    lines_of_code: int
    blank_lines: int
    comment_lines: int
    complexity: int
    imports: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "path": self.path,
            "language": self.language,
            "lines_of_code": self.lines_of_code,
            "blank_lines": self.blank_lines,
            "comment_lines": self.comment_lines,
            "complexity": self.complexity,
            "imports": self.imports,
            "classes": self.classes,
            "functions": self.functions,
        }


@dataclass
class CodebaseMetrics:
    """Overall codebase metrics."""

    total_files: int
    total_lines: int
    total_code_lines: int
    total_blank_lines: int
    total_comment_lines: int
    avg_complexity: float
    languages: Dict[str, int]  # language -> file count
    file_types: Dict[str, int]  # extension -> file count
    test_coverage: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_files": self.total_files,
            "total_lines": self.total_lines,
            "total_code_lines": self.total_code_lines,
            "total_blank_lines": self.total_blank_lines,
            "total_comment_lines": self.total_comment_lines,
            "avg_complexity": self.avg_complexity,
            "languages": self.languages,
            "file_types": self.file_types,
            "test_coverage": self.test_coverage,
        }


@dataclass
class DependencyInfo:
    """Information about project dependencies."""

    package_managers: List[str]  # pip, npm, yarn, etc.
    dependencies: Dict[str, List[str]]  # manager -> list of packages
    outdated: List[str] = field(default_factory=list)
    security_issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "package_managers": self.package_managers,
            "dependencies": self.dependencies,
            "outdated": self.outdated,
            "security_issues": self.security_issues,
        }


@dataclass
class CodebaseAnalysis:
    """Complete codebase analysis result."""

    repository_path: str
    analyzed_at: datetime
    metrics: CodebaseMetrics
    dependencies: DependencyInfo
    file_structure: Dict[str, Any]
    file_metrics: List[FileMetrics]
    patterns: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "repository_path": self.repository_path,
            "analyzed_at": self.analyzed_at.isoformat(),
            "metrics": self.metrics.to_dict(),
            "dependencies": self.dependencies.to_dict(),
            "file_structure": self.file_structure,
            "file_metrics": [fm.to_dict() for fm in self.file_metrics],
            "patterns": self.patterns,
        }


class CodebaseAnalyzer:
    """Analyzes codebase structure and extracts metrics.

    Responsibilities:
    - Scan repository file structure
    - Extract code metrics (LOC, complexity, etc.)
    - Identify dependencies
    - Detect technology stack
    - Analyze patterns and conventions
    """

    # File extensions to analyze
    CODE_EXTENSIONS = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
        ".java": "java",
        ".go": "go",
        ".rb": "ruby",
        ".php": "php",
        ".c": "c",
        ".cpp": "cpp",
        ".rs": "rust",
        ".kt": "kotlin",
        ".swift": "swift",
    }

    # Directories to ignore
    IGNORE_DIRS = {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        "build",
        "dist",
        "target",
        ".idea",
        ".vscode",
    }

    # Dependency files
    DEPENDENCY_FILES = {
        "requirements.txt": "pip",
        "Pipfile": "pipenv",
        "setup.py": "setuptools",
        "package.json": "npm",
        "yarn.lock": "yarn",
        "Gemfile": "bundler",
        "go.mod": "go",
        "Cargo.toml": "cargo",
    }

    def __init__(self, repository_path: str, logger: AuditLogger):
        """Initialize codebase analyzer.

        Args:
            repository_path: Path to repository to analyze
            logger: Audit logger
        """
        self.repository_path = Path(repository_path).resolve()
        self.logger = logger

        if not self.repository_path.exists():
            raise ValueError(f"Repository path does not exist: {repository_path}")

    def analyze(self) -> CodebaseAnalysis:
        """Analyze the codebase comprehensively.

        Returns:
            CodebaseAnalysis with complete analysis
        """
        self.logger.info(
            "Starting codebase analysis",
            repository=str(self.repository_path),
        )

        # Scan file structure
        file_structure = self._scan_file_structure()

        # Collect file metrics
        file_metrics = self._analyze_files()

        # Calculate overall metrics
        metrics = self._calculate_metrics(file_metrics)

        # Analyze dependencies
        dependencies = self._analyze_dependencies()

        # Detect patterns
        patterns = self._detect_patterns(file_metrics)

        analysis = CodebaseAnalysis(
            repository_path=str(self.repository_path),
            analyzed_at=datetime.now(timezone.utc),
            metrics=metrics,
            dependencies=dependencies,
            file_structure=file_structure,
            file_metrics=file_metrics,
            patterns=patterns,
        )

        self.logger.info(
            "Codebase analysis complete",
            total_files=metrics.total_files,
            total_lines=metrics.total_lines,
            languages=list(metrics.languages.keys()),
        )

        return analysis

    def _scan_file_structure(self) -> Dict[str, Any]:
        """Scan repository file structure.

        Returns:
            Nested dictionary representing file structure
        """
        structure: Dict[str, Any] = {}

        for root, dirs, files in os.walk(self.repository_path):
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]

            rel_root = os.path.relpath(root, self.repository_path)
            if rel_root == ".":
                current = structure
            else:
                parts = rel_root.split(os.sep)
                current = structure
                for part in parts:
                    if part not in current:
                        current[part] = {}
                    current = current[part]

            # Add files
            for file in files:
                ext = os.path.splitext(file)[1]
                if ext in self.CODE_EXTENSIONS or file in self.DEPENDENCY_FILES:
                    current[file] = "file"

        return structure

    def _analyze_files(self) -> List[FileMetrics]:
        """Analyze all code files in repository.

        Returns:
            List of FileMetrics for each file
        """
        file_metrics = []

        for root, dirs, files in os.walk(self.repository_path):
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]

            for file in files:
                ext = os.path.splitext(file)[1]
                if ext not in self.CODE_EXTENSIONS:
                    continue

                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, self.repository_path)

                try:
                    metrics = self._analyze_single_file(file_path, ext)
                    if metrics:
                        file_metrics.append(metrics)
                except Exception as e:
                    self.logger.warning(
                        "Failed to analyze file",
                        file=rel_path,
                        error=str(e),
                    )

        return file_metrics

    def _analyze_single_file(self, file_path: str, ext: str) -> Optional[FileMetrics]:
        """Analyze a single code file.

        Args:
            file_path: Path to file
            ext: File extension

        Returns:
            FileMetrics if successful, None otherwise
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except (UnicodeDecodeError, PermissionError):
            return None

        lines = content.split("\n")
        language = self.CODE_EXTENSIONS[ext]
        rel_path = os.path.relpath(file_path, self.repository_path)

        # Count lines
        code_lines = 0
        blank_lines = 0
        comment_lines = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                blank_lines += 1
            elif stripped.startswith("#") or stripped.startswith("//"):
                comment_lines += 1
            else:
                code_lines += 1

        # Extract imports, classes, functions (Python only for now)
        imports = []
        classes = []
        functions = []
        complexity = 0

        if language == "python":
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.append(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            imports.append(node.module)
                    elif isinstance(node, ast.ClassDef):
                        classes.append(node.name)
                    elif isinstance(node, ast.FunctionDef):
                        functions.append(node.name)
                        # Simple complexity: count branches
                        complexity += sum(
                            1
                            for n in ast.walk(node)
                            if isinstance(n, (ast.If, ast.For, ast.While, ast.Try))
                        )
            except SyntaxError:
                pass

        return FileMetrics(
            path=rel_path,
            language=language,
            lines_of_code=code_lines,
            blank_lines=blank_lines,
            comment_lines=comment_lines,
            complexity=complexity,
            imports=list(set(imports)),
            classes=classes,
            functions=functions,
        )

    def _calculate_metrics(self, file_metrics: List[FileMetrics]) -> CodebaseMetrics:
        """Calculate overall codebase metrics.

        Args:
            file_metrics: List of file metrics

        Returns:
            CodebaseMetrics with aggregated data
        """
        if not file_metrics:
            return CodebaseMetrics(
                total_files=0,
                total_lines=0,
                total_code_lines=0,
                total_blank_lines=0,
                total_comment_lines=0,
                avg_complexity=0.0,
                languages={},
                file_types={},
            )

        total_code = sum(fm.lines_of_code for fm in file_metrics)
        total_blank = sum(fm.blank_lines for fm in file_metrics)
        total_comment = sum(fm.comment_lines for fm in file_metrics)
        total_complexity = sum(fm.complexity for fm in file_metrics)

        # Count languages
        languages: Dict[str, int] = {}
        for fm in file_metrics:
            languages[fm.language] = languages.get(fm.language, 0) + 1

        # Count file types
        file_types: Dict[str, int] = {}
        for fm in file_metrics:
            ext = os.path.splitext(fm.path)[1]
            file_types[ext] = file_types.get(ext, 0) + 1

        return CodebaseMetrics(
            total_files=len(file_metrics),
            total_lines=total_code + total_blank + total_comment,
            total_code_lines=total_code,
            total_blank_lines=total_blank,
            total_comment_lines=total_comment,
            avg_complexity=(
                total_complexity / len(file_metrics) if file_metrics else 0.0
            ),
            languages=languages,
            file_types=file_types,
        )

    def _analyze_dependencies(self) -> DependencyInfo:
        """Analyze project dependencies.

        Returns:
            DependencyInfo with dependency data
        """
        package_managers = []
        dependencies = {}

        for dep_file, manager in self.DEPENDENCY_FILES.items():
            file_path = self.repository_path / dep_file
            if file_path.exists():
                package_managers.append(manager)
                deps = self._parse_dependency_file(file_path, manager)
                if deps:
                    dependencies[manager] = deps

        return DependencyInfo(
            package_managers=package_managers,
            dependencies=dependencies,
        )

    def _parse_dependency_file(self, file_path: Path, manager: str) -> List[str]:
        """Parse a dependency file.

        Args:
            file_path: Path to dependency file
            manager: Package manager name

        Returns:
            List of dependency names
        """
        deps = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if manager == "pip":
                # Parse requirements.txt
                for line in content.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        # Extract package name (before ==, >=, etc.)
                        match = re.match(r"^([a-zA-Z0-9_-]+)", line)
                        if match:
                            deps.append(match.group(1))

            elif manager == "npm" or manager == "yarn":
                # Parse package.json
                try:
                    data = json.loads(content)
                    if "dependencies" in data:
                        deps.extend(data["dependencies"].keys())
                    if "devDependencies" in data:
                        deps.extend(data["devDependencies"].keys())
                except json.JSONDecodeError:
                    pass

        except Exception as e:
            self.logger.warning(
                "Failed to parse dependency file",
                file=str(file_path),
                error=str(e),
            )

        return deps

    def _detect_patterns(self, file_metrics: List[FileMetrics]) -> Dict[str, Any]:
        """Detect code patterns and conventions.

        Args:
            file_metrics: List of file metrics

        Returns:
            Dictionary of detected patterns
        """
        patterns: Dict[str, Any] = {}

        # Detect test files
        test_files = [
            fm.path
            for fm in file_metrics
            if "test" in fm.path.lower() or fm.path.startswith("tests/")
        ]
        patterns["test_files_count"] = len(test_files)
        patterns["has_tests"] = len(test_files) > 0

        # Detect documentation
        doc_files = [
            str(f.relative_to(self.repository_path))
            for f in self.repository_path.rglob("*.md")
        ]
        patterns["documentation_files"] = doc_files
        patterns["has_documentation"] = len(doc_files) > 0

        # Detect common frameworks/patterns
        all_imports = set()
        for fm in file_metrics:
            all_imports.update(fm.imports)

        frameworks = {
            "flask": "flask" in all_imports,
            "django": "django" in all_imports,
            "fastapi": "fastapi" in all_imports,
            "react": any("react" in imp for imp in all_imports),
            "pytest": "pytest" in all_imports,
        }
        patterns["frameworks"] = {k: v for k, v in frameworks.items() if v}

        # Detect architecture patterns
        has_models = any("models" in fm.path for fm in file_metrics)
        has_views = any("views" in fm.path for fm in file_metrics)
        has_controllers = any("controllers" in fm.path for fm in file_metrics)

        if has_models and has_views:
            patterns["architecture_pattern"] = "MVC-like"
        else:
            patterns["architecture_pattern"] = "Unknown"

        return patterns
