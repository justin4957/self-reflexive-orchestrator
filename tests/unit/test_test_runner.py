"""Unit tests for TestRunner."""

import unittest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path
import subprocess

from src.integrations.test_runner import (
    TestRunner,
    TestFramework,
    TestStatus,
    TestResult,
    TestFailure,
    TestRunnerError,
    TestFrameworkNotFoundError,
)
from src.core.logger import AuditLogger


class TestTestRunner(unittest.TestCase):
    """Test cases for TestRunner."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.repo_path = Path("/fake/repo")

        # Don't verify path exists in tests
        with patch.object(Path, 'exists', return_value=True):
            self.runner = TestRunner(
                repo_path=self.repo_path,
                logger=self.logger,
                timeout=30,
            )

    def test_initialization(self):
        """Test test runner initialization."""
        self.assertEqual(self.runner.repo_path, self.repo_path)
        self.assertEqual(self.runner.logger, self.logger)
        self.assertEqual(self.runner.timeout, 30)

    def test_initialization_invalid_path(self):
        """Test initialization with invalid path raises error."""
        with self.assertRaises(TestRunnerError):
            TestRunner(
                repo_path=Path("/nonexistent"),
                logger=self.logger,
            )

    @patch('pathlib.Path.exists')
    def test_detect_framework_pytest(self, mock_exists):
        """Test pytest framework detection."""
        # Mock pytest.ini exists
        def exists_side_effect(path_self):
            return str(path_self).endswith('pytest.ini')

        with patch.object(Path, 'exists', side_effect=lambda: exists_side_effect(Path('pytest.ini'))):
            mock_exists.return_value = True
            with patch.object(Path, '__truediv__', return_value=Path('/fake/repo/pytest.ini')):
                with patch.object(Path, 'exists', return_value=True):
                    framework = self.runner.detect_framework()
                    self.assertEqual(framework, TestFramework.PYTEST)

    def test_detect_framework_jest(self):
        """Test jest framework detection."""
        # Mock exists to only return True for jest.config.js
        original_exists = Path.exists

        def exists_side_effect(path_self):
            path_str = str(path_self)
            return 'jest.config.js' in path_str

        with patch.object(Path, 'exists', new=lambda self: exists_side_effect(self)):
            with patch.object(Path, 'glob', return_value=[]):
                framework = self.runner.detect_framework()
                self.assertEqual(framework, TestFramework.JEST)

    def test_detect_framework_fallback_pytest(self):
        """Test fallback to pytest when tests directory exists."""
        with patch('pathlib.Path.glob', return_value=[]):
            # Mock tests directory exists
            original_truediv = Path.__truediv__
            def mock_truediv(self, other):
                result = original_truediv(self, other)
                # Make tests directory return True for exists()
                if 'tests' in str(result):
                    with patch.object(type(result), 'exists', return_value=True):
                        return result
                return result

            with patch.object(Path, '__truediv__', mock_truediv):
                with patch.object(Path, 'exists', return_value=True):
                    framework = self.runner.detect_framework()
                    self.assertEqual(framework, TestFramework.PYTEST)

    @patch('pathlib.Path.glob')
    @patch('pathlib.Path.exists')
    def test_detect_framework_not_found(self, mock_exists, mock_glob):
        """Test framework detection failure."""
        mock_glob.return_value = []
        mock_exists.return_value = False

        with self.assertRaises(TestFrameworkNotFoundError):
            self.runner.detect_framework()

    def test_build_test_command_pytest(self):
        """Test pytest command building."""
        command = self.runner._build_test_command(TestFramework.PYTEST)
        self.assertEqual(command[:3], ['python', '-m', 'pytest'])
        self.assertIn('-v', command)

    def test_build_test_command_pytest_with_paths(self):
        """Test pytest command with specific paths."""
        command = self.runner._build_test_command(
            TestFramework.PYTEST,
            test_paths=['tests/test_foo.py']
        )
        self.assertIn('tests/test_foo.py', command)

    def test_build_test_command_jest(self):
        """Test jest command building."""
        command = self.runner._build_test_command(TestFramework.JEST)
        self.assertEqual(command[:2], ['npm', 'test'])

    def test_build_test_command_go(self):
        """Test go test command building."""
        command = self.runner._build_test_command(TestFramework.GO_TEST)
        self.assertIn('go', command)
        self.assertIn('test', command)

    def test_build_test_command_unsupported(self):
        """Test unsupported framework raises error."""
        with self.assertRaises(TestRunnerError):
            self.runner._build_test_command(TestFramework.UNKNOWN)

    def test_parse_pytest_output_success(self):
        """Test parsing successful pytest output."""
        output = """
============================= test session starts ==============================
collected 3 items

tests/test_foo.py::test_one PASSED                                       [ 33%]
tests/test_foo.py::test_two PASSED                                       [ 66%]
tests/test_foo.py::test_three PASSED                                     [100%]

============================== 3 passed in 0.05s ===============================
"""
        result = self.runner._parse_pytest_output(output, 0)

        self.assertEqual(result.framework, TestFramework.PYTEST)
        self.assertEqual(result.total_tests, 3)
        self.assertEqual(result.passed, 3)
        self.assertEqual(result.failed, 0)
        self.assertTrue(result.success)
        self.assertEqual(len(result.failures), 0)

    def test_parse_pytest_output_with_failures(self):
        """Test parsing pytest output with failures."""
        output = """
============================= test session starts ==============================
collected 3 items

tests/test_foo.py::test_one PASSED                                       [ 33%]
tests/test_foo.py::test_two FAILED                                       [ 66%]
tests/test_foo.py::test_three PASSED                                     [100%]

=================================== FAILURES ===================================
_________________________________ test_two _____________________________________

    def test_two():
>       assert 1 == 2
E       AssertionError: assert 1 == 2

tests/test_foo.py:10: AssertionError
=========================== 1 failed, 2 passed in 0.10s ========================
"""
        result = self.runner._parse_pytest_output(output, 1)

        self.assertEqual(result.total_tests, 3)
        self.assertEqual(result.passed, 2)
        self.assertEqual(result.failed, 1)
        self.assertFalse(result.success)
        self.assertEqual(len(result.failures), 1)

        failure = result.failures[0]
        self.assertIn('test_two', failure.test_name)
        self.assertIn('AssertionError', failure.error_message)

    def test_parse_unittest_output(self):
        """Test parsing unittest output."""
        output = """
test_one (tests.test_foo.TestFoo) ... ok
test_two (tests.test_foo.TestFoo) ... FAIL
test_three (tests.test_foo.TestFoo) ... ok

======================================================================
FAIL: test_two (tests.test_foo.TestFoo)
----------------------------------------------------------------------
AssertionError: 1 != 2

----------------------------------------------------------------------
Ran 3 tests in 0.001s

FAILED (failures=1)
"""
        result = self.runner._parse_unittest_output(output, 1)

        self.assertEqual(result.framework, TestFramework.UNITTEST)
        self.assertEqual(result.total_tests, 3)
        self.assertEqual(result.passed, 2)
        self.assertEqual(result.failed, 1)
        self.assertFalse(result.success)

    def test_parse_jest_output(self):
        """Test parsing Jest output."""
        output = """
 FAIL  tests/example.test.js
  ● test suite › test name

    expect(received).toBe(expected)

    Expected: 2
    Received: 1

      4 |   test('test name', () => {
    > 5 |     expect(1).toBe(2);
        |               ^
      6 |   });

Tests: 1 failed, 2 passed, 3 total
Time: 1.234 s
"""
        result = self.runner._parse_jest_output(output, 1)

        self.assertEqual(result.framework, TestFramework.JEST)
        self.assertEqual(result.total_tests, 3)
        self.assertEqual(result.passed, 2)
        self.assertEqual(result.failed, 1)

    def test_parse_gotest_output(self):
        """Test parsing go test output."""
        output = """
=== RUN   TestFoo
--- PASS: TestFoo (0.00s)
=== RUN   TestBar
--- FAIL: TestBar (0.01s)
    bar_test.go:10: Expected 2, got 1
FAIL
FAIL    example.com/package    0.01s
"""
        result = self.runner._parse_gotest_output(output, 1)

        self.assertEqual(result.framework, TestFramework.GO_TEST)
        self.assertEqual(result.passed, 1)
        self.assertEqual(result.failed, 1)

    @patch('subprocess.run')
    @patch.object(TestRunner, 'detect_framework')
    def test_run_tests_success(self, mock_detect, mock_run):
        """Test successful test execution."""
        mock_detect.return_value = TestFramework.PYTEST

        mock_result = Mock()
        mock_result.stdout = "====== 3 passed in 0.05s ======"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = self.runner.run_tests()

        self.assertTrue(result.success)
        self.assertEqual(result.framework, TestFramework.PYTEST)
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_run_tests_with_framework_specified(self, mock_run):
        """Test running tests with specific framework."""
        mock_result = Mock()
        mock_result.stdout = "====== 3 passed in 0.05s ======"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = self.runner.run_tests(framework=TestFramework.PYTEST)

        self.assertEqual(result.framework, TestFramework.PYTEST)
        self.assertTrue(result.success)

    @patch('subprocess.run')
    def test_run_tests_timeout(self, mock_run):
        """Test test execution timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=['pytest'], timeout=30)

        result = self.runner.run_tests(framework=TestFramework.PYTEST)

        self.assertFalse(result.success)
        self.assertEqual(result.exit_code, -1)
        self.assertIn('timed out', result.output)

    @patch('subprocess.run')
    def test_run_tests_exception(self, mock_run):
        """Test test execution exception handling."""
        mock_run.side_effect = Exception("Test execution failed")

        result = self.runner.run_tests(framework=TestFramework.PYTEST)

        self.assertFalse(result.success)
        self.assertIn('error', result.output.lower())

    def test_is_test_file_python(self):
        """Test Python test file detection."""
        self.assertTrue(self.runner._is_test_file(Path('test_foo.py')))
        self.assertTrue(self.runner._is_test_file(Path('foo_test.py')))
        self.assertFalse(self.runner._is_test_file(Path('foo.py')))

    def test_is_test_file_javascript(self):
        """Test JavaScript test file detection."""
        self.assertTrue(self.runner._is_test_file(Path('foo.test.js')))
        self.assertTrue(self.runner._is_test_file(Path('foo.spec.js')))
        self.assertFalse(self.runner._is_test_file(Path('foo.js')))

    def test_is_test_file_go(self):
        """Test Go test file detection."""
        self.assertTrue(self.runner._is_test_file(Path('foo_test.go')))
        self.assertFalse(self.runner._is_test_file(Path('foo.go')))

    def test_find_corresponding_test(self):
        """Test finding corresponding test file."""
        source_file = Path('/fake/repo/src/foo.py')

        # Mock exists to return True for tests directory and test_foo.py
        def exists_side_effect(path_self):
            path_str = str(path_self)
            # Return True for tests directory and test_foo.py file
            return 'tests' in path_str or 'test_foo.py' in path_str

        with patch.object(Path, 'exists', new=lambda self: exists_side_effect(self)):
            test_file = self.runner._find_corresponding_test(source_file)

            # Should find test_foo.py in tests directory
            self.assertIsNotNone(test_file)

    @patch('pathlib.Path.exists')
    def test_get_changed_test_files(self, mock_exists):
        """Test getting test files for changed source files."""
        mock_exists.return_value = True

        # Test file is already a test
        test_files = self.runner.get_changed_test_files(['tests/test_foo.py'])
        self.assertIn('tests/test_foo.py', test_files)

    def test_test_failure_to_dict(self):
        """Test TestFailure to_dict conversion."""
        failure = TestFailure(
            test_name="test_example",
            test_file="test_foo.py",
            error_message="AssertionError: 1 != 2",
            stack_trace="Traceback...",
            line_number=42,
            failure_type="assertion",
        )

        failure_dict = failure.to_dict()

        self.assertEqual(failure_dict['test_name'], "test_example")
        self.assertEqual(failure_dict['test_file'], "test_foo.py")
        self.assertEqual(failure_dict['line_number'], 42)
        self.assertEqual(failure_dict['failure_type'], "assertion")

    def test_test_result_to_dict(self):
        """Test TestResult to_dict conversion."""
        result = TestResult(
            framework=TestFramework.PYTEST,
            total_tests=10,
            passed=8,
            failed=2,
            skipped=0,
            execution_time=1.5,
            failures=[],
            exit_code=1,
        )

        result_dict = result.to_dict()

        self.assertEqual(result_dict['framework'], 'pytest')
        self.assertEqual(result_dict['total_tests'], 10)
        self.assertEqual(result_dict['passed'], 8)
        self.assertEqual(result_dict['failed'], 2)
        self.assertFalse(result_dict['success'])
        self.assertTrue(result_dict['has_failures'])

    def test_test_result_success_property(self):
        """Test TestResult success property."""
        # All passed
        result = TestResult(
            framework=TestFramework.PYTEST,
            total_tests=3,
            passed=3,
            failed=0,
            skipped=0,
            execution_time=1.0,
            exit_code=0,
        )
        self.assertTrue(result.success)

        # Some failed
        result.failed = 1
        self.assertFalse(result.success)

        # Non-zero exit code
        result.failed = 0
        result.exit_code = 1
        self.assertFalse(result.success)

    def test_test_result_has_failures_property(self):
        """Test TestResult has_failures property."""
        result = TestResult(
            framework=TestFramework.PYTEST,
            total_tests=3,
            passed=3,
            failed=0,
            skipped=0,
            execution_time=1.0,
        )
        self.assertFalse(result.has_failures)

        result.failed = 1
        self.assertTrue(result.has_failures)

        result.failed = 0
        result.failures = [TestFailure("test", "file", "error")]
        self.assertTrue(result.has_failures)

    def test_framework_enum_values(self):
        """Test TestFramework enum values."""
        self.assertEqual(TestFramework.PYTEST.value, "pytest")
        self.assertEqual(TestFramework.JEST.value, "jest")
        self.assertEqual(TestFramework.GO_TEST.value, "go_test")

    def test_status_enum_values(self):
        """Test TestStatus enum values."""
        self.assertEqual(TestStatus.PASSED.value, "passed")
        self.assertEqual(TestStatus.FAILED.value, "failed")
        self.assertEqual(TestStatus.SKIPPED.value, "skipped")


if __name__ == '__main__':
    unittest.main()
