"""Unit tests for CodebaseAnalyzer."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from src.analyzers.codebase_analyzer import (
    CodebaseAnalysis,
    CodebaseAnalyzer,
    CodebaseMetrics,
    DependencyInfo,
    FileMetrics,
)
from src.core.logger import AuditLogger


class TestCodebaseAnalyzer(unittest.TestCase):
    """Test cases for CodebaseAnalyzer."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)

        # Create temporary test repository
        self.test_repo = tempfile.mkdtemp()
        self.test_path = Path(self.test_repo)

        # Create test file structure
        self._create_test_repository()

        self.analyzer = CodebaseAnalyzer(
            repository_path=str(self.test_path),
            logger=self.logger,
        )

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.test_repo)

    def _create_test_repository(self):
        """Create a test repository structure."""
        # Create src directory with Python files
        src_dir = self.test_path / "src"
        src_dir.mkdir()

        # Create a simple Python file
        (src_dir / "main.py").write_text(
            """
# Main module
import os
import sys

class MyClass:
    def __init__(self):
        self.value = 0

    def process(self, data):
        if data:
            for item in data:
                self.value += 1
        return self.value
"""
        )

        # Create another Python file with more complexity
        (src_dir / "utils.py").write_text(
            """
\"\"\"Utility functions.\"\"\"

def calculate(x, y):
    try:
        if x > y:
            return x / y
        elif x < y:
            return y / x
        else:
            return 1
    except ZeroDivisionError:
        return 0

def validate(value):
    while value > 0:
        value -= 1
    return value
"""
        )

        # Create tests directory
        tests_dir = self.test_path / "tests"
        tests_dir.mkdir()

        (tests_dir / "test_main.py").write_text(
            """
import unittest
from src.main import MyClass

class TestMyClass(unittest.TestCase):
    def test_init(self):
        obj = MyClass()
        self.assertEqual(obj.value, 0)
"""
        )

        # Create README
        (self.test_path / "README.md").write_text("# Test Project\n\nA test project.")

        # Create requirements.txt
        (self.test_path / "requirements.txt").write_text(
            """
requests>=2.28.0
pytest==7.4.0
black
# Development dependencies
isort>=5.0.0
"""
        )

        # Create package.json
        (self.test_path / "package.json").write_text(
            """
{
  "name": "test-project",
  "dependencies": {
    "react": "^18.0.0",
    "axios": "^1.0.0"
  },
  "devDependencies": {
    "jest": "^29.0.0"
  }
}
"""
        )

    def test_initialization(self):
        """Test analyzer initialization."""
        # Use resolve() to handle macOS /private/var symlinks
        self.assertEqual(
            self.analyzer.repository_path.resolve(), self.test_path.resolve()
        )
        self.assertTrue(self.analyzer.repository_path.exists())

    def test_initialization_invalid_path(self):
        """Test initialization with invalid path."""
        with self.assertRaises(ValueError):
            CodebaseAnalyzer("/nonexistent/path", self.logger)

    def test_scan_file_structure(self):
        """Test file structure scanning."""
        structure = self.analyzer._scan_file_structure()

        # Should contain src directory
        self.assertIn("src", structure)
        self.assertIn("main.py", structure["src"])
        self.assertIn("utils.py", structure["src"])

        # Should contain tests directory
        self.assertIn("tests", structure)

        # Should contain dependency files
        self.assertIn("requirements.txt", structure)
        self.assertIn("package.json", structure)

    def test_analyze_single_file_python(self):
        """Test analyzing a single Python file."""
        file_path = str(self.test_path / "src" / "main.py")
        metrics = self.analyzer._analyze_single_file(file_path, ".py")

        self.assertIsNotNone(metrics)
        self.assertEqual(metrics.language, "python")
        self.assertGreater(metrics.lines_of_code, 0)
        self.assertGreater(metrics.comment_lines, 0)

        # Should extract imports
        self.assertIn("os", metrics.imports)
        self.assertIn("sys", metrics.imports)

        # Should extract classes
        self.assertIn("MyClass", metrics.classes)

        # Should extract functions
        self.assertIn("__init__", metrics.functions)
        self.assertIn("process", metrics.functions)

        # Should calculate complexity
        self.assertGreater(metrics.complexity, 0)

    def test_analyze_single_file_with_complexity(self):
        """Test analyzing file with control flow complexity."""
        file_path = str(self.test_path / "src" / "utils.py")
        metrics = self.analyzer._analyze_single_file(file_path, ".py")

        self.assertIsNotNone(metrics)
        # utils.py has if/elif/try/while statements
        self.assertGreater(metrics.complexity, 2)

        # Should extract functions
        self.assertIn("calculate", metrics.functions)
        self.assertIn("validate", metrics.functions)

    def test_analyze_single_file_unicode_error(self):
        """Test handling of file with encoding errors."""
        # Create a file with binary content
        binary_file = self.test_path / "binary.py"
        binary_file.write_bytes(b"\x80\x81\x82")

        metrics = self.analyzer._analyze_single_file(str(binary_file), ".py")

        # Should return None for unreadable files
        self.assertIsNone(metrics)

    def test_analyze_files(self):
        """Test analyzing all files in repository."""
        file_metrics = self.analyzer._analyze_files()

        # Should find Python files
        self.assertGreater(len(file_metrics), 0)

        # All should be Python files
        for fm in file_metrics:
            self.assertEqual(fm.language, "python")

        # Should have analyzed src files
        src_files = [fm for fm in file_metrics if "src/" in fm.path]
        self.assertGreater(len(src_files), 0)

    def test_calculate_metrics(self):
        """Test calculating overall metrics."""
        file_metrics = self.analyzer._analyze_files()
        metrics = self.analyzer._calculate_metrics(file_metrics)

        self.assertGreater(metrics.total_files, 0)
        self.assertGreater(metrics.total_lines, 0)
        self.assertGreater(metrics.total_code_lines, 0)
        self.assertGreaterEqual(metrics.total_blank_lines, 0)
        self.assertGreaterEqual(metrics.total_comment_lines, 0)

        # Should have Python language
        self.assertIn("python", metrics.languages)

        # Should have .py file type
        self.assertIn(".py", metrics.file_types)

        # Average complexity should be calculated
        self.assertGreaterEqual(metrics.avg_complexity, 0.0)

    def test_calculate_metrics_empty(self):
        """Test calculating metrics with no files."""
        metrics = self.analyzer._calculate_metrics([])

        self.assertEqual(metrics.total_files, 0)
        self.assertEqual(metrics.total_lines, 0)
        self.assertEqual(metrics.avg_complexity, 0.0)
        self.assertEqual(len(metrics.languages), 0)

    def test_analyze_dependencies_pip(self):
        """Test analyzing pip dependencies."""
        dependencies = self.analyzer._analyze_dependencies()

        # Should find pip manager
        self.assertIn("pip", dependencies.package_managers)

        # Should parse dependencies
        self.assertIn("pip", dependencies.dependencies)
        pip_deps = dependencies.dependencies["pip"]

        self.assertIn("requests", pip_deps)
        self.assertIn("pytest", pip_deps)
        self.assertIn("black", pip_deps)
        self.assertIn("isort", pip_deps)

    def test_analyze_dependencies_npm(self):
        """Test analyzing npm dependencies."""
        dependencies = self.analyzer._analyze_dependencies()

        # Should find npm manager
        self.assertIn("npm", dependencies.package_managers)

        # Should parse dependencies
        self.assertIn("npm", dependencies.dependencies)
        npm_deps = dependencies.dependencies["npm"]

        self.assertIn("react", npm_deps)
        self.assertIn("axios", npm_deps)
        self.assertIn("jest", npm_deps)

    def test_parse_dependency_file_pip(self):
        """Test parsing requirements.txt."""
        file_path = self.test_path / "requirements.txt"
        deps = self.analyzer._parse_dependency_file(file_path, "pip")

        self.assertGreater(len(deps), 0)
        self.assertIn("requests", deps)
        self.assertIn("pytest", deps)
        # Should not include comments
        self.assertNotIn("# Development dependencies", deps)

    def test_parse_dependency_file_npm(self):
        """Test parsing package.json."""
        file_path = self.test_path / "package.json"
        deps = self.analyzer._parse_dependency_file(file_path, "npm")

        self.assertGreater(len(deps), 0)
        self.assertIn("react", deps)
        self.assertIn("axios", deps)
        self.assertIn("jest", deps)

    def test_detect_patterns(self):
        """Test pattern detection."""
        file_metrics = self.analyzer._analyze_files()
        patterns = self.analyzer._detect_patterns(file_metrics)

        # Should detect test files
        self.assertIn("test_files_count", patterns)
        self.assertGreater(patterns["test_files_count"], 0)
        self.assertTrue(patterns["has_tests"])

        # Should detect documentation
        self.assertIn("has_documentation", patterns)
        self.assertTrue(patterns["has_documentation"])
        self.assertIn("documentation_files", patterns)

        # Should have frameworks dict
        self.assertIn("frameworks", patterns)

    def test_detect_patterns_frameworks(self):
        """Test framework detection from imports."""
        # Add a file with framework imports
        (self.test_path / "src" / "app.py").write_text(
            """
import flask
import django
from django.http import HttpResponse
"""
        )

        file_metrics = self.analyzer._analyze_files()
        patterns = self.analyzer._detect_patterns(file_metrics)

        # Should detect flask and django
        frameworks = patterns.get("frameworks", {})
        self.assertTrue(frameworks.get("flask", False))
        # Django import detection checks for 'django' in imports
        self.assertTrue(frameworks.get("django", False))

    def test_detect_architecture_pattern_mvc(self):
        """Test MVC-like architecture pattern detection."""
        # Create models and views directories
        models_dir = self.test_path / "src" / "models"
        models_dir.mkdir()
        (models_dir / "user.py").write_text("class User: pass")

        views_dir = self.test_path / "src" / "views"
        views_dir.mkdir()
        (views_dir / "user_view.py").write_text("def user_view(): pass")

        file_metrics = self.analyzer._analyze_files()
        patterns = self.analyzer._detect_patterns(file_metrics)

        # Should detect MVC-like pattern
        self.assertEqual(patterns["architecture_pattern"], "MVC-like")

    def test_analyze_complete(self):
        """Test complete analysis."""
        analysis = self.analyzer.analyze()

        # Verify analysis result
        self.assertIsInstance(analysis, CodebaseAnalysis)
        # Use resolve() to handle macOS /private/var symlinks
        self.assertEqual(
            Path(analysis.repository_path).resolve(), self.test_path.resolve()
        )

        # Verify metrics
        self.assertGreater(analysis.metrics.total_files, 0)
        self.assertGreater(analysis.metrics.total_lines, 0)
        self.assertIn("python", analysis.metrics.languages)

        # Verify dependencies
        self.assertIn("pip", analysis.dependencies.package_managers)
        self.assertIn("npm", analysis.dependencies.package_managers)

        # Verify file structure
        self.assertIn("src", analysis.file_structure)

        # Verify file metrics
        self.assertGreater(len(analysis.file_metrics), 0)

        # Verify patterns
        self.assertTrue(analysis.patterns["has_tests"])
        self.assertTrue(analysis.patterns["has_documentation"])

    def test_file_metrics_to_dict(self):
        """Test FileMetrics to_dict conversion."""
        metrics = FileMetrics(
            path="src/test.py",
            language="python",
            lines_of_code=100,
            blank_lines=10,
            comment_lines=20,
            complexity=5,
            imports=["os", "sys"],
            classes=["MyClass"],
            functions=["my_function"],
        )

        result = metrics.to_dict()

        self.assertEqual(result["path"], "src/test.py")
        self.assertEqual(result["language"], "python")
        self.assertEqual(result["lines_of_code"], 100)
        self.assertEqual(len(result["imports"]), 2)
        self.assertEqual(len(result["classes"]), 1)

    def test_codebase_metrics_to_dict(self):
        """Test CodebaseMetrics to_dict conversion."""
        metrics = CodebaseMetrics(
            total_files=10,
            total_lines=1000,
            total_code_lines=700,
            total_blank_lines=150,
            total_comment_lines=150,
            avg_complexity=5.2,
            languages={"python": 8, "javascript": 2},
            file_types={".py": 8, ".js": 2},
            test_coverage=85.5,
        )

        result = metrics.to_dict()

        self.assertEqual(result["total_files"], 10)
        self.assertEqual(result["avg_complexity"], 5.2)
        self.assertEqual(result["test_coverage"], 85.5)
        self.assertIn("python", result["languages"])

    def test_dependency_info_to_dict(self):
        """Test DependencyInfo to_dict conversion."""
        info = DependencyInfo(
            package_managers=["pip", "npm"],
            dependencies={"pip": ["requests", "pytest"], "npm": ["react"]},
            outdated=["requests"],
            security_issues=["vulnerability in requests"],
        )

        result = info.to_dict()

        self.assertEqual(len(result["package_managers"]), 2)
        self.assertEqual(len(result["dependencies"]["pip"]), 2)
        self.assertEqual(len(result["outdated"]), 1)

    def test_codebase_analysis_to_dict(self):
        """Test CodebaseAnalysis to_dict conversion."""
        analysis = self.analyzer.analyze()
        result = analysis.to_dict()

        self.assertIn("repository_path", result)
        self.assertIn("analyzed_at", result)
        self.assertIn("metrics", result)
        self.assertIn("dependencies", result)
        self.assertIn("file_structure", result)
        self.assertIn("file_metrics", result)
        self.assertIn("patterns", result)

    def test_ignore_directories(self):
        """Test that ignored directories are not analyzed."""
        # Create ignored directories
        (self.test_path / ".git").mkdir()
        (self.test_path / ".git" / "config").write_text("test")

        (self.test_path / "node_modules").mkdir()
        (self.test_path / "node_modules" / "lib.js").write_text("test")

        (self.test_path / "__pycache__").mkdir()
        (self.test_path / "__pycache__" / "cache.pyc").write_text("test")

        # Analyze
        file_metrics = self.analyzer._analyze_files()

        # Should not include files from ignored directories
        for fm in file_metrics:
            self.assertNotIn(".git", fm.path)
            self.assertNotIn("node_modules", fm.path)
            self.assertNotIn("__pycache__", fm.path)

    def test_code_extensions(self):
        """Test that CODE_EXTENSIONS are properly defined."""
        self.assertIn(".py", CodebaseAnalyzer.CODE_EXTENSIONS)
        self.assertIn(".js", CodebaseAnalyzer.CODE_EXTENSIONS)
        self.assertIn(".ts", CodebaseAnalyzer.CODE_EXTENSIONS)
        self.assertEqual(CodebaseAnalyzer.CODE_EXTENSIONS[".py"], "python")

    def test_dependency_files(self):
        """Test that DEPENDENCY_FILES are properly defined."""
        self.assertIn("requirements.txt", CodebaseAnalyzer.DEPENDENCY_FILES)
        self.assertIn("package.json", CodebaseAnalyzer.DEPENDENCY_FILES)
        self.assertEqual(CodebaseAnalyzer.DEPENDENCY_FILES["requirements.txt"], "pip")


if __name__ == "__main__":
    unittest.main()
