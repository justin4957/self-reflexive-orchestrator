"""Context builder for analyzing repository patterns and building context database.

Extracts code style, architecture patterns, and domain context to enhance prompts.
"""

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.logger import AuditLogger


@dataclass
class CodeStyleContext:
    """Code style and formatting context."""

    language: str
    version: Optional[str]
    formatter: Optional[str]
    linter: Optional[str]
    naming_conventions: Dict[str, str]
    import_style: str
    comment_style: str
    line_length: int
    uses_type_hints: bool


@dataclass
class ArchitectureContext:
    """Architecture and design patterns context."""

    framework: Optional[str]
    design_patterns: List[str]
    module_structure: Dict[str, str]
    testing_framework: Optional[str]
    async_patterns: bool
    dependency_injection: bool
    common_directories: List[str]


@dataclass
class DomainContext:
    """Domain-specific context."""

    project_type: str  # "web_api", "cli", "library", "data_pipeline", etc.
    domain: str  # "finance", "ml", "devops", etc.
    key_terminology: List[str]
    business_logic_patterns: List[str]


@dataclass
class HistoricalContext:
    """Historical context from past successes."""

    similar_issues: List[Dict[str, Any]]
    successful_patterns: List[str]
    avoided_patterns: List[str]
    common_solutions: Dict[str, str]


@dataclass
class RepositoryContext:
    """Complete repository context."""

    code_style: CodeStyleContext
    architecture: ArchitectureContext
    domain: DomainContext
    historical: HistoricalContext
    last_updated: str


class ContextBuilder:
    """Builds context by analyzing repository patterns.

    Responsibilities:
    - Analyze code style and formatting
    - Extract architecture patterns
    - Identify domain context
    - Build historical context from analytics
    - Store context in database
    - Provide context for prompts
    """

    def __init__(self, repo_path: Path, logger: AuditLogger):
        """Initialize context builder.

        Args:
            repo_path: Path to repository root
            logger: Audit logger instance
        """
        self.repo_path = repo_path
        self.logger = logger
        self.context: Optional[RepositoryContext] = None

    def analyze_repository(self) -> RepositoryContext:
        """Analyze repository and build complete context.

        Returns:
            RepositoryContext with all analyzed information
        """
        self.logger.info("repository_analysis_started", repo_path=str(self.repo_path))

        # Analyze different aspects
        code_style = self._analyze_code_style()
        architecture = self._analyze_architecture()
        domain = self._analyze_domain()
        historical = self._analyze_historical()

        # Build complete context
        from datetime import datetime, timezone

        self.context = RepositoryContext(
            code_style=code_style,
            architecture=architecture,
            domain=domain,
            historical=historical,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )

        self.logger.info(
            "repository_analysis_completed",
            language=code_style.language,
            framework=architecture.framework,
            project_type=domain.project_type,
        )

        return self.context

    def _analyze_code_style(self) -> CodeStyleContext:
        """Analyze code style from repository files.

        Returns:
            CodeStyleContext with style information
        """
        # Detect language
        language = self._detect_primary_language()
        version = self._detect_language_version()

        # Check for formatters
        formatter = self._detect_formatter()
        linter = self._detect_linter()

        # Analyze naming conventions
        naming_conventions = self._analyze_naming_conventions()

        # Analyze import style
        import_style = self._analyze_import_style()

        # Detect comment style
        comment_style = self._analyze_comment_style()

        # Check for type hints
        uses_type_hints = self._check_type_hints()

        # Determine line length
        line_length = self._determine_line_length()

        return CodeStyleContext(
            language=language,
            version=version,
            formatter=formatter,
            linter=linter,
            naming_conventions=naming_conventions,
            import_style=import_style,
            comment_style=comment_style,
            line_length=line_length,
            uses_type_hints=uses_type_hints,
        )

    def _analyze_architecture(self) -> ArchitectureContext:
        """Analyze architecture patterns.

        Returns:
            ArchitectureContext with architecture information
        """
        # Detect framework
        framework = self._detect_framework()

        # Identify design patterns
        design_patterns = self._identify_design_patterns()

        # Analyze module structure
        module_structure = self._analyze_module_structure()

        # Detect testing framework
        testing_framework = self._detect_testing_framework()

        # Check for async patterns
        async_patterns = self._check_async_patterns()

        # Check for dependency injection
        dependency_injection = self._check_dependency_injection()

        # Get common directories
        common_directories = self._get_common_directories()

        return ArchitectureContext(
            framework=framework,
            design_patterns=design_patterns,
            module_structure=module_structure,
            testing_framework=testing_framework,
            async_patterns=async_patterns,
            dependency_injection=dependency_injection,
            common_directories=common_directories,
        )

    def _analyze_domain(self) -> DomainContext:
        """Analyze domain context.

        Returns:
            DomainContext with domain information
        """
        # Determine project type
        project_type = self._determine_project_type()

        # Infer domain
        domain = self._infer_domain()

        # Extract key terminology
        key_terminology = self._extract_key_terminology()

        # Identify business logic patterns
        business_logic_patterns = self._identify_business_logic_patterns()

        return DomainContext(
            project_type=project_type,
            domain=domain,
            key_terminology=key_terminology,
            business_logic_patterns=business_logic_patterns,
        )

    def _analyze_historical(self) -> HistoricalContext:
        """Analyze historical context from past work.

        Returns:
            HistoricalContext with historical information
        """
        # This would integrate with analytics database
        # For now, return empty context
        return HistoricalContext(
            similar_issues=[],
            successful_patterns=[],
            avoided_patterns=[],
            common_solutions={},
        )

    # Helper methods for code style analysis

    def _detect_primary_language(self) -> str:
        """Detect primary programming language."""
        # Count files by extension
        extensions = {}
        for py_file in self.repo_path.rglob("*.py"):
            extensions[".py"] = extensions.get(".py", 0) + 1
        for js_file in self.repo_path.rglob("*.js"):
            extensions[".js"] = extensions.get(".js", 0) + 1
        for ts_file in self.repo_path.rglob("*.ts"):
            extensions[".ts"] = extensions.get(".ts", 0) + 1

        if extensions:
            most_common = max(extensions.items(), key=lambda x: x[1])
            ext_to_lang = {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript"}
            return ext_to_lang.get(most_common[0], "Unknown")

        return "Unknown"

    def _detect_language_version(self) -> Optional[str]:
        """Detect language version from config files."""
        # Check for Python version
        pyproject = self.repo_path / "pyproject.toml"
        if pyproject.exists():
            content = pyproject.read_text()
            if "python_version" in content or "requires-python" in content:
                # Simple extraction
                match = re.search(r'["\'](3\.\d+)["\']', content)
                if match:
                    return match.group(1)

        setup_py = self.repo_path / "setup.py"
        if setup_py.exists():
            content = setup_py.read_text()
            match = re.search(r'python_requires=["\']>=?(3\.\d+)', content)
            if match:
                return match.group(1)

        return None

    def _detect_formatter(self) -> Optional[str]:
        """Detect code formatter."""
        if (self.repo_path / "pyproject.toml").exists():
            content = (self.repo_path / "pyproject.toml").read_text()
            if "[tool.black]" in content:
                return "black"
            if "[tool.autopep8]" in content:
                return "autopep8"

        if (self.repo_path / ".prettierrc").exists():
            return "prettier"

        return None

    def _detect_linter(self) -> Optional[str]:
        """Detect linter configuration."""
        if (self.repo_path / "pyproject.toml").exists():
            content = (self.repo_path / "pyproject.toml").read_text()
            if "[tool.pylint]" in content:
                return "pylint"
            if "[tool.flake8]" in content:
                return "flake8"
            if "[tool.ruff]" in content:
                return "ruff"

        if (self.repo_path / ".pylintrc").exists():
            return "pylint"
        if (self.repo_path / ".flake8").exists():
            return "flake8"

        return None

    def _analyze_naming_conventions(self) -> Dict[str, str]:
        """Analyze naming conventions from code."""
        conventions = {
            "functions": "snake_case",  # Default for Python
            "classes": "PascalCase",
            "constants": "UPPER_CASE",
            "variables": "snake_case",
        }
        return conventions

    def _analyze_import_style(self) -> str:
        """Analyze import organization style."""
        # Check for isort configuration
        if (self.repo_path / "pyproject.toml").exists():
            content = (self.repo_path / "pyproject.toml").read_text()
            if "[tool.isort]" in content:
                return "isort organized"

        return "standard"

    def _analyze_comment_style(self) -> str:
        """Analyze comment and docstring style."""
        # Check for docstring style in config
        if (self.repo_path / "pyproject.toml").exists():
            content = (self.repo_path / "pyproject.toml").read_text()
            if "google" in content.lower():
                return "Google style"
            if "numpy" in content.lower():
                return "NumPy style"

        # Sample some Python files
        python_files = list(self.repo_path.rglob("*.py"))[:10]
        for py_file in python_files:
            try:
                content = py_file.read_text()
                if '"""' in content and "Args:" in content and "Returns:" in content:
                    return "Google style"
            except:
                pass

        return "standard"

    def _check_type_hints(self) -> bool:
        """Check if codebase uses type hints."""
        python_files = list(self.repo_path.rglob("*.py"))[:10]
        for py_file in python_files:
            try:
                content = py_file.read_text()
                if " -> " in content or ": " in content:
                    # Simple check for type hints
                    if re.search(r":\s*\w+\s*=", content) or re.search(
                        r"->\s*\w+:", content
                    ):
                        return True
            except:
                pass
        return False

    def _determine_line_length(self) -> int:
        """Determine line length limit."""
        if (self.repo_path / "pyproject.toml").exists():
            content = (self.repo_path / "pyproject.toml").read_text()
            match = re.search(r"line[-_]length\s*=\s*(\d+)", content)
            if match:
                return int(match.group(1))

        return 88  # Black default

    # Helper methods for architecture analysis

    def _detect_framework(self) -> Optional[str]:
        """Detect web/app framework."""
        requirements = self.repo_path / "requirements.txt"
        if requirements.exists():
            content = requirements.read_text().lower()
            if "fastapi" in content:
                return "FastAPI"
            if "flask" in content:
                return "Flask"
            if "django" in content:
                return "Django"
            if "click" in content:
                return "Click (CLI)"

        pyproject = self.repo_path / "pyproject.toml"
        if pyproject.exists():
            content = pyproject.read_text().lower()
            if "fastapi" in content:
                return "FastAPI"
            if "flask" in content:
                return "Flask"

        return None

    def _identify_design_patterns(self) -> List[str]:
        """Identify design patterns in use."""
        patterns = []

        # Check for common patterns
        python_files = list(self.repo_path.rglob("*.py"))
        for py_file in python_files:
            try:
                content = py_file.read_text()
                if "class.*Factory" in content or "FactoryPattern" in content:
                    patterns.append("Factory")
                if "Singleton" in content:
                    patterns.append("Singleton")
                if "class.*Strategy" in content:
                    patterns.append("Strategy")
                if "class.*Observer" in content:
                    patterns.append("Observer")
            except:
                pass

        return list(set(patterns))

    def _analyze_module_structure(self) -> Dict[str, str]:
        """Analyze module organization structure."""
        structure = {}

        # Check for common directories
        if (self.repo_path / "src").exists():
            structure["source"] = "src/"
        if (self.repo_path / "tests").exists():
            structure["tests"] = "tests/"
        if (self.repo_path / "docs").exists():
            structure["docs"] = "docs/"

        return structure

    def _detect_testing_framework(self) -> Optional[str]:
        """Detect testing framework."""
        requirements = self.repo_path / "requirements.txt"
        if requirements.exists():
            content = requirements.read_text().lower()
            if "pytest" in content:
                return "pytest"
            if "unittest" in content:
                return "unittest"

        # Check for pytest.ini or test files
        if (self.repo_path / "pytest.ini").exists():
            return "pytest"

        test_files = list(self.repo_path.rglob("test_*.py"))
        if test_files:
            return "pytest"  # Assumed

        return None

    def _check_async_patterns(self) -> bool:
        """Check if async/await patterns are used."""
        python_files = list(self.repo_path.rglob("*.py"))[:10]
        for py_file in python_files:
            try:
                content = py_file.read_text()
                if "async def" in content or "await " in content:
                    return True
            except:
                pass
        return False

    def _check_dependency_injection(self) -> bool:
        """Check for dependency injection patterns."""
        # Simple check for common DI frameworks
        requirements = self.repo_path / "requirements.txt"
        if requirements.exists():
            content = requirements.read_text().lower()
            if "injector" in content or "dependency-injector" in content:
                return True

        return False

    def _get_common_directories(self) -> List[str]:
        """Get list of common directories."""
        dirs = []
        for d in self.repo_path.iterdir():
            if d.is_dir() and not d.name.startswith("."):
                dirs.append(d.name)
        return sorted(dirs[:10])  # Limit to 10

    # Helper methods for domain analysis

    def _determine_project_type(self) -> str:
        """Determine project type."""
        # Check for web API indicators
        if self._detect_framework() in ["FastAPI", "Flask", "Django"]:
            return "web_api"

        # Check for CLI indicators
        if self._detect_framework() == "Click (CLI)":
            return "cli"

        # Check for library indicators
        if (self.repo_path / "setup.py").exists() or (
            self.repo_path / "pyproject.toml"
        ).exists():
            return "library"

        return "application"

    def _infer_domain(self) -> str:
        """Infer technical domain from codebase."""
        # Simple keyword-based inference
        readme = self.repo_path / "README.md"
        if readme.exists():
            content = readme.read_text().lower()
            if any(
                word in content
                for word in ["machine learning", "ml", "ai", "neural", "model"]
            ):
                return "machine_learning"
            if any(word in content for word in ["api", "rest", "graphql", "web"]):
                return "web_services"
            if any(word in content for word in ["devops", "ci/cd", "automation"]):
                return "devops"
            if any(word in content for word in ["data", "pipeline", "etl"]):
                return "data_engineering"

        return "general"

    def _extract_key_terminology(self) -> List[str]:
        """Extract key domain terminology."""
        # This would analyze README and docstrings
        # For now, return empty list
        return []

    def _identify_business_logic_patterns(self) -> List[str]:
        """Identify business logic patterns."""
        # This would analyze code patterns
        # For now, return empty list
        return []

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary.

        Returns:
            Dictionary representation of context
        """
        if self.context is None:
            return {}
        return asdict(self.context)

    def save_to_file(self, file_path: Path):
        """Save context to JSON file.

        Args:
            file_path: Path to save context
        """
        if self.context is None:
            raise ValueError("No context to save. Run analyze_repository() first.")

        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

        self.logger.info("context_saved", file_path=str(file_path))

    @classmethod
    def load_from_file(cls, file_path: Path, logger: AuditLogger) -> "ContextBuilder":
        """Load context from JSON file.

        Args:
            file_path: Path to load context from
            logger: Audit logger instance

        Returns:
            ContextBuilder instance with loaded context
        """
        with open(file_path, "r") as f:
            data = json.load(f)

        # Reconstruct context
        builder = cls(repo_path=Path("."), logger=logger)
        builder.context = RepositoryContext(
            code_style=CodeStyleContext(**data["code_style"]),
            architecture=ArchitectureContext(**data["architecture"]),
            domain=DomainContext(**data["domain"]),
            historical=HistoricalContext(**data["historical"]),
            last_updated=data["last_updated"],
        )

        logger.info("context_loaded", file_path=str(file_path))
        return builder
