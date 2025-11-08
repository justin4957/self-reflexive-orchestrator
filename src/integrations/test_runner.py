"""Test runner integration for executing and analyzing test results.

Supports multiple test frameworks:
- Python: pytest, unittest
- JavaScript: jest, mocha
- Go: go test
- Ruby: rspec
"""

import subprocess
import json
import re
from typing import List, Optional, Dict, Any, Set
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

from ..core.logger import AuditLogger


class TestFramework(Enum):
    """Supported test frameworks."""
    PYTEST = "pytest"
    UNITTEST = "unittest"
    JEST = "jest"
    MOCHA = "mocha"
    GO_TEST = "go_test"
    RSPEC = "rspec"
    UNKNOWN = "unknown"


class TestStatus(Enum):
    """Test execution status."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestFailure:
    """Represents a single test failure."""
    test_name: str
    test_file: str
    error_message: str
    stack_trace: Optional[str] = None
    line_number: Optional[int] = None
    failure_type: str = "assertion"  # assertion, exception, timeout

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "test_name": self.test_name,
            "test_file": self.test_file,
            "error_message": self.error_message,
            "stack_trace": self.stack_trace,
            "line_number": self.line_number,
            "failure_type": self.failure_type,
        }


@dataclass
class TestResult:
    """Complete test execution result."""
    framework: TestFramework
    total_tests: int
    passed: int
    failed: int
    skipped: int
    execution_time: float
    failures: List[TestFailure] = field(default_factory=list)
    output: str = ""
    exit_code: int = 0

    @property
    def success(self) -> bool:
        """Check if all tests passed."""
        return self.failed == 0 and self.exit_code == 0

    @property
    def has_failures(self) -> bool:
        """Check if any tests failed."""
        return self.failed > 0 or bool(self.failures)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "framework": self.framework.value,
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "execution_time": self.execution_time,
            "success": self.success,
            "has_failures": self.has_failures,
            "failures": [f.to_dict() for f in self.failures],
            "exit_code": self.exit_code,
        }


class TestRunnerError(Exception):
    """Base exception for test runner errors."""
    pass


class TestFrameworkNotFoundError(TestRunnerError):
    """Raised when test framework cannot be detected or is not installed."""
    pass


class TestRunner:
    """Test runner for multiple frameworks.

    Responsibilities:
    - Detect test framework in repository
    - Execute tests with appropriate commands
    - Parse test output and extract results
    - Identify failing tests with error messages
    - Support selective test execution
    """

    # Framework detection patterns
    FRAMEWORK_INDICATORS = {
        TestFramework.PYTEST: ["pytest.ini", "pyproject.toml", "setup.cfg"],
        TestFramework.UNITTEST: ["test_*.py", "*_test.py"],
        TestFramework.JEST: ["jest.config.js", "jest.config.ts", "package.json"],
        TestFramework.MOCHA: [".mocharc.json", ".mocharc.js"],
        TestFramework.GO_TEST: ["*_test.go"],
        TestFramework.RSPEC: [".rspec", "spec/spec_helper.rb"],
    }

    def __init__(
        self,
        repo_path: Path,
        logger: AuditLogger,
        timeout: int = 300,  # 5 minutes default
    ):
        """Initialize test runner.

        Args:
            repo_path: Path to repository root
            logger: Audit logger instance
            timeout: Test execution timeout in seconds
        """
        self.repo_path = Path(repo_path).resolve()
        self.logger = logger
        self.timeout = timeout

        # Verify repository exists
        if not self.repo_path.exists():
            raise TestRunnerError(f"Repository path does not exist: {repo_path}")

    def detect_framework(self) -> TestFramework:
        """Detect test framework used in repository.

        Returns:
            Detected TestFramework

        Raises:
            TestFrameworkNotFoundError: If no framework can be detected
        """
        self.logger.debug("Detecting test framework", repo_path=str(self.repo_path))

        # Check for framework indicators
        for framework, indicators in self.FRAMEWORK_INDICATORS.items():
            for indicator in indicators:
                # Check for exact files or glob patterns
                if "*" in indicator:
                    # Glob pattern
                    matches = list(self.repo_path.glob(f"**/{indicator}"))
                    if matches:
                        self.logger.info(
                            "Detected test framework",
                            framework=framework.value,
                            indicator=indicator,
                        )
                        return framework
                else:
                    # Exact file
                    if (self.repo_path / indicator).exists():
                        self.logger.info(
                            "Detected test framework",
                            framework=framework.value,
                            indicator=indicator,
                        )
                        return framework

        # Default to pytest for Python projects with tests directory
        if (self.repo_path / "tests").exists():
            self.logger.info("Defaulting to pytest based on tests directory")
            return TestFramework.PYTEST

        raise TestFrameworkNotFoundError(
            "Could not detect test framework. Supported: pytest, jest, go test, rspec"
        )

    def run_tests(
        self,
        test_paths: Optional[List[str]] = None,
        framework: Optional[TestFramework] = None,
    ) -> TestResult:
        """Run tests with detected or specified framework.

        Args:
            test_paths: Optional specific test files/paths to run
            framework: Optional specific framework to use

        Returns:
            TestResult with execution details
        """
        # Detect framework if not specified
        if framework is None:
            framework = self.detect_framework()

        self.logger.info(
            "Running tests",
            framework=framework.value,
            test_paths=test_paths,
            timeout=self.timeout,
        )

        # Build test command
        command = self._build_test_command(framework, test_paths)

        # Execute tests
        try:
            result = subprocess.run(
                command,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                shell=False,
            )

            # Parse output based on framework
            test_result = self._parse_output(framework, result.stdout, result.stderr, result.returncode)

            self.logger.info(
                "Test execution completed",
                framework=framework.value,
                total_tests=test_result.total_tests,
                passed=test_result.passed,
                failed=test_result.failed,
                success=test_result.success,
            )

            return test_result

        except subprocess.TimeoutExpired:
            self.logger.error(f"Test execution timed out after {self.timeout}s")
            return TestResult(
                framework=framework,
                total_tests=0,
                passed=0,
                failed=0,
                skipped=0,
                execution_time=self.timeout,
                output=f"Test execution timed out after {self.timeout}s",
                exit_code=-1,
            )
        except Exception as e:
            self.logger.error(f"Test execution failed: {e}", exc_info=True)
            return TestResult(
                framework=framework,
                total_tests=0,
                passed=0,
                failed=0,
                skipped=0,
                execution_time=0.0,
                output=f"Test execution error: {str(e)}",
                exit_code=-1,
            )

    def _build_test_command(
        self,
        framework: TestFramework,
        test_paths: Optional[List[str]] = None,
    ) -> List[str]:
        """Build test command for framework.

        Args:
            framework: Test framework to use
            test_paths: Optional specific paths to test

        Returns:
            Command as list of strings
        """
        test_paths = test_paths or []

        if framework == TestFramework.PYTEST:
            cmd = ["python", "-m", "pytest", "-v", "--tb=short"]
            if test_paths:
                cmd.extend(test_paths)
            return cmd

        elif framework == TestFramework.UNITTEST:
            cmd = ["python", "-m", "unittest", "discover", "-v"]
            if test_paths:
                cmd.extend(test_paths)
            return cmd

        elif framework == TestFramework.JEST:
            cmd = ["npm", "test", "--", "--verbose"]
            if test_paths:
                cmd.extend(test_paths)
            return cmd

        elif framework == TestFramework.MOCHA:
            cmd = ["npm", "test"]
            if test_paths:
                cmd.extend(test_paths)
            return cmd

        elif framework == TestFramework.GO_TEST:
            cmd = ["go", "test", "-v", "./..."]
            if test_paths:
                # Replace ./... with specific paths
                cmd = ["go", "test", "-v"] + test_paths
            return cmd

        elif framework == TestFramework.RSPEC:
            cmd = ["rspec", "--format", "documentation"]
            if test_paths:
                cmd.extend(test_paths)
            return cmd

        else:
            raise TestRunnerError(f"Unsupported framework: {framework}")

    def _parse_output(
        self,
        framework: TestFramework,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> TestResult:
        """Parse test output based on framework.

        Args:
            framework: Test framework used
            stdout: Standard output from test execution
            stderr: Standard error from test execution
            exit_code: Exit code from test execution

        Returns:
            Parsed TestResult
        """
        output = stdout + "\n" + stderr

        if framework == TestFramework.PYTEST:
            return self._parse_pytest_output(output, exit_code)
        elif framework == TestFramework.UNITTEST:
            return self._parse_unittest_output(output, exit_code)
        elif framework == TestFramework.JEST:
            return self._parse_jest_output(output, exit_code)
        elif framework == TestFramework.GO_TEST:
            return self._parse_gotest_output(output, exit_code)
        elif framework == TestFramework.RSPEC:
            return self._parse_rspec_output(output, exit_code)
        else:
            # Generic parsing
            return TestResult(
                framework=framework,
                total_tests=0,
                passed=0,
                failed=0,
                skipped=0,
                execution_time=0.0,
                output=output,
                exit_code=exit_code,
            )

    def _parse_pytest_output(self, output: str, exit_code: int) -> TestResult:
        """Parse pytest output."""
        failures = []

        # Extract test counts from summary line
        # Example: "====== 1 failed, 2 passed in 0.50s ======"
        summary_match = re.search(
            r'(\d+)\s+failed.*?(\d+)\s+passed.*?in\s+([\d.]+)s',
            output
        )

        if summary_match:
            failed = int(summary_match.group(1))
            passed = int(summary_match.group(2))
            exec_time = float(summary_match.group(3))
        else:
            # Try alternative format
            failed_match = re.search(r'(\d+)\s+failed', output)
            passed_match = re.search(r'(\d+)\s+passed', output)
            time_match = re.search(r'in\s+([\d.]+)s', output)

            failed = int(failed_match.group(1)) if failed_match else 0
            passed = int(passed_match.group(1)) if passed_match else 0
            exec_time = float(time_match.group(1)) if time_match else 0.0

        total_tests = failed + passed

        # Extract failures
        # Look for test_file.py::test_name FAILED
        # Format: "tests/test_foo.py::test_two FAILED                                       [ 66%]"
        failure_pattern = r'(.*?)::(.*?)\s+FAILED'
        for match in re.finditer(failure_pattern, output):
            test_file = match.group(1).strip()
            test_name = match.group(2).strip()
            error_msg = None

            # Try to extract stack trace and error from FAILURES section
            stack_trace = None
            # Look for underlined test name section
            trace_pattern = rf'_+\s*{re.escape(test_name)}\s*_+\s*\n(.*?)(?=\n_+\s*[a-zA-Z]|====|$)'
            trace_match = re.search(trace_pattern, output, re.DOTALL)
            if trace_match:
                stack_trace = trace_match.group(1).strip()
                # Extract error message from stack trace if not in FAILED line
                if not error_msg:
                    # Look for E       AssertionError or similar
                    error_match = re.search(r'E\s+(.*?)(?=\n)', stack_trace)
                    if error_match:
                        error_msg = error_match.group(1).strip()
                    else:
                        # Look for last line with file:line: error
                        error_match = re.search(r':\d+:\s+(.+)$', stack_trace, re.MULTILINE)
                        if error_match:
                            error_msg = error_match.group(1).strip()

            if not error_msg:
                error_msg = "Test failed"

            failures.append(TestFailure(
                test_name=test_name,
                test_file=test_file,
                error_message=error_msg,
                stack_trace=stack_trace,
            ))

        return TestResult(
            framework=TestFramework.PYTEST,
            total_tests=total_tests,
            passed=passed,
            failed=failed,
            skipped=0,
            execution_time=exec_time,
            failures=failures,
            output=output,
            exit_code=exit_code,
        )

    def _parse_unittest_output(self, output: str, exit_code: int) -> TestResult:
        """Parse unittest output."""
        failures = []

        # Extract test counts
        # Example: "Ran 3 tests in 0.001s\nFAILED (failures=1)"
        ran_match = re.search(r'Ran\s+(\d+)\s+tests?\s+in\s+([\d.]+)s', output)
        failed_match = re.search(r'FAILED\s+\(.*?failures?=(\d+)', output)

        total_tests = int(ran_match.group(1)) if ran_match else 0
        exec_time = float(ran_match.group(2)) if ran_match else 0.0
        failed = int(failed_match.group(1)) if failed_match else 0
        passed = total_tests - failed

        # Extract failures
        # Look for FAIL: test_name (module.TestClass)
        failure_pattern = r'FAIL:\s+(.*?)\s+\((.*?)\)\n(.*?)(?=\n\n|$)'
        for match in re.finditer(failure_pattern, output, re.DOTALL):
            test_name = match.group(1)
            test_class = match.group(2)
            error_msg = match.group(3).strip()

            failures.append(TestFailure(
                test_name=test_name,
                test_file=test_class,
                error_message=error_msg,
            ))

        return TestResult(
            framework=TestFramework.UNITTEST,
            total_tests=total_tests,
            passed=passed,
            failed=failed,
            skipped=0,
            execution_time=exec_time,
            failures=failures,
            output=output,
            exit_code=exit_code,
        )

    def _parse_jest_output(self, output: str, exit_code: int) -> TestResult:
        """Parse Jest output."""
        failures = []

        # Extract test counts from Jest summary
        # Example: "Tests: 1 failed, 2 passed, 3 total"
        failed_match = re.search(r'Tests:.*?(\d+)\s+failed', output)
        passed_match = re.search(r'(\d+)\s+passed', output)
        total_match = re.search(r'(\d+)\s+total', output)
        time_match = re.search(r'Time:\s+([\d.]+)\s*s', output)

        failed = int(failed_match.group(1)) if failed_match else 0
        passed = int(passed_match.group(1)) if passed_match else 0
        total_tests = int(total_match.group(1)) if total_match else (failed + passed)
        exec_time = float(time_match.group(1)) if time_match else 0.0

        # Extract failures
        # Jest format: ● test suite › test name
        failure_pattern = r'●\s+(.*?)\s+›\s+(.*?)\n\s+(.*?)(?=\n\s+●|$)'
        for match in re.finditer(failure_pattern, output, re.DOTALL):
            test_suite = match.group(1)
            test_name = match.group(2)
            error_msg = match.group(3).strip()

            failures.append(TestFailure(
                test_name=test_name,
                test_file=test_suite,
                error_message=error_msg,
            ))

        return TestResult(
            framework=TestFramework.JEST,
            total_tests=total_tests,
            passed=passed,
            failed=failed,
            skipped=0,
            execution_time=exec_time,
            failures=failures,
            output=output,
            exit_code=exit_code,
        )

    def _parse_gotest_output(self, output: str, exit_code: int) -> TestResult:
        """Parse go test output."""
        failures = []

        # Count PASS and FAIL lines (but only test results, not final FAIL line)
        pass_count = len(re.findall(r'^---\s+PASS:', output, re.MULTILINE))
        fail_count = len(re.findall(r'^---\s+FAIL:', output, re.MULTILINE))

        # Extract execution time
        time_match = re.search(r'FAIL.*?(\d+\.\d+)s', output)
        exec_time = float(time_match.group(1)) if time_match else 0.0

        # Extract failures
        # Go format: --- FAIL: TestName (0.00s)
        failure_pattern = r'---\s+FAIL:\s+(.*?)\s+\(([\d.]+)s\)\n\s+(.*?)(?=\n---|$)'
        for match in re.finditer(failure_pattern, output, re.DOTALL):
            test_name = match.group(1)
            error_msg = match.group(3).strip()

            failures.append(TestFailure(
                test_name=test_name,
                test_file="go_test",
                error_message=error_msg,
            ))

        return TestResult(
            framework=TestFramework.GO_TEST,
            total_tests=pass_count + fail_count,
            passed=pass_count,
            failed=fail_count,
            skipped=0,
            execution_time=exec_time,
            failures=failures,
            output=output,
            exit_code=exit_code,
        )

    def _parse_rspec_output(self, output: str, exit_code: int) -> TestResult:
        """Parse rspec output."""
        failures = []

        # Extract test counts
        # Example: "3 examples, 1 failure"
        examples_match = re.search(r'(\d+)\s+examples?', output)
        failures_match = re.search(r'(\d+)\s+failures?', output)
        time_match = re.search(r'Finished in\s+([\d.]+)\s+seconds?', output)

        total_tests = int(examples_match.group(1)) if examples_match else 0
        failed = int(failures_match.group(1)) if failures_match else 0
        passed = total_tests - failed
        exec_time = float(time_match.group(1)) if time_match else 0.0

        # Extract failures
        # RSpec format: Failure/Error: expect(...)
        failure_pattern = r'Failure/Error:\s+(.*?)\n\s+(.*?)(?=\n\s+#|$)'
        for match in re.finditer(failure_pattern, output, re.DOTALL):
            test_code = match.group(1).strip()
            error_msg = match.group(2).strip()

            failures.append(TestFailure(
                test_name=test_code,
                test_file="rspec",
                error_message=error_msg,
            ))

        return TestResult(
            framework=TestFramework.RSPEC,
            total_tests=total_tests,
            passed=passed,
            failed=failed,
            skipped=0,
            execution_time=exec_time,
            failures=failures,
            output=output,
            exit_code=exit_code,
        )

    def get_changed_test_files(self, changed_files: List[str]) -> List[str]:
        """Get test files corresponding to changed source files.

        Args:
            changed_files: List of changed source file paths

        Returns:
            List of test file paths to run
        """
        test_files = []

        for file_path in changed_files:
            path = Path(file_path)

            # If it's already a test file, include it
            if self._is_test_file(path):
                test_files.append(file_path)
                continue

            # Try to find corresponding test file
            test_file = self._find_corresponding_test(path)
            if test_file and test_file.exists():
                test_files.append(str(test_file.relative_to(self.repo_path)))

        return test_files

    def _is_test_file(self, path: Path) -> bool:
        """Check if file is a test file."""
        test_patterns = [
            'test_*.py', '*_test.py',  # Python
            '*.test.js', '*.spec.js',  # JavaScript
            '*_test.go',               # Go
            '*_spec.rb',               # Ruby
        ]

        for pattern in test_patterns:
            if path.match(pattern):
                return True

        return False

    def _find_corresponding_test(self, source_file: Path) -> Optional[Path]:
        """Find corresponding test file for source file."""
        # Try common test file patterns
        stem = source_file.stem
        suffix = source_file.suffix

        test_patterns = [
            f"test_{stem}{suffix}",
            f"{stem}_test{suffix}",
            f"{stem}.test{suffix}",
            f"{stem}.spec{suffix}",
            f"{stem}_spec{suffix}",
        ]

        # Search in tests directory and parallel structure
        search_dirs = [
            self.repo_path / "tests",
            self.repo_path / "test",
            source_file.parent / "tests",
            source_file.parent / "test",
            source_file.parent,  # Same directory
        ]

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            for pattern in test_patterns:
                test_file = search_dir / pattern
                if test_file.exists():
                    return test_file

        return None
