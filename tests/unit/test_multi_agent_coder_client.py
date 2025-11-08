"""Unit tests for MultiAgentCoderClient."""

import unittest
from unittest.mock import Mock, patch, MagicMock
import subprocess
from pathlib import Path

from src.integrations.multi_agent_coder_client import (
    MultiAgentCoderClient,
    MultiAgentStrategy,
    MultiAgentResponse,
)
from src.core.logger import AuditLogger


class TestMultiAgentCoderClient(unittest.TestCase):
    """Test cases for MultiAgentCoderClient."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = Mock(spec=AuditLogger)
        self.executable_path = "/fake/path/to/multi_agent_coder"

        # Create client with mocked path validation
        with patch.object(Path, 'exists', return_value=True):
            self.client = MultiAgentCoderClient(
                multi_agent_coder_path=self.executable_path,
                logger=self.logger,
            )

    def test_initialization(self):
        """Test client initialization."""
        self.assertEqual(str(self.client.executable_path), self.executable_path)
        self.assertEqual(self.client.default_strategy, MultiAgentStrategy.ALL)
        self.assertEqual(self.client.total_calls, 0)
        self.assertEqual(self.client.total_tokens, 0)
        self.assertEqual(self.client.total_cost, 0.0)

    def test_initialization_file_not_found(self):
        """Test initialization with missing executable."""
        with patch.object(Path, 'exists', return_value=False):
            with self.assertRaises(FileNotFoundError):
                MultiAgentCoderClient(
                    multi_agent_coder_path="/nonexistent/path",
                    logger=self.logger,
                )

    @patch('subprocess.run')
    def test_query_success(self, mock_run):
        """Test successful query execution."""
        # Mock successful subprocess execution
        mock_result = MagicMock()
        mock_result.stdout = """
╔═══ ANTHROPIC ═══╗
This is a test response from Anthropic.
Analysis indicates this is a bug with complexity 7.

╔═══ DEEPSEEK ═══╗
DeepSeek response here.
Complexity score: 6
"""
        mock_result.stderr = "7121 tokens, $0.0656"
        mock_run.return_value = mock_result

        response = self.client.query("Test prompt", timeout=60)

        # Verify subprocess call
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        self.assertIn("Test prompt", call_args[0][0])
        self.assertEqual(call_args[1]['timeout'], 60)
        self.assertTrue(call_args[1]['capture_output'])

        # Verify response
        self.assertTrue(response.success)
        self.assertIn('anthropic', response.providers)
        self.assertIn('deepseek', response.providers)
        self.assertGreater(response.total_tokens, 0)
        self.assertGreater(response.total_cost, 0.0)

        # Verify statistics updated
        self.assertEqual(self.client.total_calls, 1)

    @patch('subprocess.run')
    def test_query_timeout(self, mock_run):
        """Test query timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=['test'], timeout=60
        )

        response = self.client.query("Test prompt", timeout=60)

        self.assertFalse(response.success)
        self.assertIsNotNone(response.error)
        self.assertIn("timed out", response.error.lower())

    @patch('subprocess.run')
    def test_query_process_error(self, mock_run):
        """Test query process error handling."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=['test'],
            stderr="Error executing multi_agent_coder"
        )

        response = self.client.query("Test prompt")

        self.assertFalse(response.success)
        self.assertIsNotNone(response.error)

    def test_parse_output_multiple_providers(self):
        """Test parsing output with multiple providers."""
        stdout = """
╔═══ ANTHROPIC ═══╗
Anthropic analysis here.
Complexity: 7

╔═══ DEEPSEEK ═══╗
DeepSeek analysis.
Score: 6

╔═══ OPENAI ═══╗
OpenAI response.
"""
        stderr = "12000 tokens, $0.10"

        response = self.client._parse_output(stdout, stderr)

        self.assertEqual(len(response.providers), 3)
        self.assertIn('anthropic', response.providers)
        self.assertIn('deepseek', response.providers)
        self.assertIn('openai', response.providers)
        self.assertIn('Anthropic analysis', response.responses['anthropic'])
        self.assertIn('DeepSeek analysis', response.responses['deepseek'])

    def test_parse_output_with_errors(self):
        """Test parsing output with provider errors."""
        stdout = """
╔═══ ANTHROPIC ═══╗
Anthropic analysis here.

╔═══ OPENAI ═══╗
Error: Invalid API key or authentication failed
"""
        stderr = "5000 tokens, $0.05"

        response = self.client._parse_output(stdout, stderr)

        # Should still parse successful providers
        self.assertIn('anthropic', response.providers)
        self.assertIn('openai', response.providers)
        # OpenAI response should be captured despite error
        self.assertIn('openai', response.responses)

    def test_parse_output_token_extraction(self):
        """Test token count extraction from output."""
        stdout = "Response text"
        stderr = "Request successful - 7,121 tokens, $0.0656"

        response = self.client._parse_output(stdout, stderr)

        self.assertGreater(response.total_tokens, 7000)
        self.assertAlmostEqual(response.total_cost, 0.0656, places=4)

    def test_parse_output_no_providers(self):
        """Test parsing output with no valid providers."""
        stdout = "No provider headers found"
        stderr = ""

        response = self.client._parse_output(stdout, stderr)

        self.assertEqual(len(response.providers), 0)
        self.assertEqual(len(response.responses), 0)
        self.assertFalse(response.success)

    @patch('subprocess.run')
    def test_analyze_issue(self, mock_run):
        """Test issue analysis method."""
        mock_result = MagicMock()
        mock_result.stdout = """
╔═══ ANTHROPIC ═══╗
Issue Type: BUG
Complexity Score: 7
Actionability: yes
"""
        mock_result.stderr = "5000 tokens, $0.04"
        mock_run.return_value = mock_result

        response = self.client.analyze_issue(
            issue_title="Test bug",
            issue_body="Bug description",
            labels=["bug", "priority-high"],
        )

        # Verify prompt construction
        call_args = mock_run.call_args[0][0]
        prompt = call_args[-1]
        self.assertIn("Test bug", prompt)
        self.assertIn("Bug description", prompt)
        self.assertIn("bug, priority-high", prompt)
        self.assertIn("Issue Type", prompt)
        self.assertIn("Complexity Score", prompt)

        # Verify response
        self.assertTrue(response.success)

    @patch('subprocess.run')
    def test_review_code(self, mock_run):
        """Test code review method."""
        mock_result = MagicMock()
        mock_result.stdout = """
╔═══ ANTHROPIC ═══╗
Code review feedback here.
"""
        mock_result.stderr = "3000 tokens, $0.03"
        mock_run.return_value = mock_result

        code = "def hello():\n    print('world')"
        response = self.client.review_code(
            code=code,
            focus_areas=["security", "performance"],
        )

        # Verify prompt construction
        call_args = mock_run.call_args[0][0]
        prompt = call_args[-1]
        self.assertIn(code, prompt)
        self.assertIn("security", prompt)
        self.assertIn("performance", prompt)

        # Verify dialectical strategy used
        self.assertIn("-s", call_args)
        strategy_idx = call_args.index("-s") + 1
        self.assertEqual(call_args[strategy_idx], "dialectical")

    def test_get_statistics(self):
        """Test statistics retrieval."""
        # Manually set some statistics
        self.client.total_calls = 5
        self.client.total_tokens = 25000
        self.client.total_cost = 0.25
        self.client.provider_usage = {"anthropic": 5, "deepseek": 3}

        stats = self.client.get_statistics()

        self.assertEqual(stats["total_calls"], 5)
        self.assertEqual(stats["total_tokens"], 25000)
        self.assertEqual(stats["total_cost"], 0.25)
        self.assertEqual(stats["average_tokens_per_call"], 5000)
        self.assertEqual(stats["average_cost_per_call"], 0.05)
        self.assertEqual(stats["provider_usage"]["anthropic"], 5)

    def test_reset_statistics(self):
        """Test statistics reset."""
        # Set some statistics
        self.client.total_calls = 5
        self.client.total_tokens = 1000
        self.client.total_cost = 0.10
        self.client.provider_usage = {"anthropic": 5}

        # Reset
        self.client.reset_statistics()

        self.assertEqual(self.client.total_calls, 0)
        self.assertEqual(self.client.total_tokens, 0)
        self.assertEqual(self.client.total_cost, 0.0)
        self.assertEqual(len(self.client.provider_usage), 0)

    @patch('subprocess.run')
    def test_query_with_custom_strategy(self, mock_run):
        """Test query with custom strategy."""
        mock_result = MagicMock()
        mock_result.stdout = "╔═══ ANTHROPIC ═══╗\nResponse"
        mock_result.stderr = "1000 tokens, $0.01"
        mock_run.return_value = mock_result

        self.client.query(
            "Test prompt",
            strategy=MultiAgentStrategy.SEQUENTIAL,
        )

        # Verify strategy in command
        call_args = mock_run.call_args[0][0]
        self.assertIn("-s", call_args)
        strategy_idx = call_args.index("-s") + 1
        self.assertEqual(call_args[strategy_idx], "sequential")

    @patch('subprocess.run')
    def test_query_with_provider_filter(self, mock_run):
        """Test query with provider filtering."""
        mock_result = MagicMock()
        mock_result.stdout = "╔═══ ANTHROPIC ═══╗\nResponse"
        mock_result.stderr = "1000 tokens, $0.01"
        mock_run.return_value = mock_result

        self.client.query(
            "Test prompt",
            providers=["anthropic", "deepseek"],
        )

        # Verify providers in command
        call_args = mock_run.call_args[0][0]
        self.assertIn("-p", call_args)
        providers_idx = call_args.index("-p") + 1
        self.assertEqual(call_args[providers_idx], "anthropic,deepseek")

    def test_response_dataclass(self):
        """Test MultiAgentResponse dataclass."""
        response = MultiAgentResponse(
            providers=["anthropic", "deepseek"],
            responses={"anthropic": "text1", "deepseek": "text2"},
            strategy="all",
            total_tokens=5000,
            total_cost=0.05,
            success=True,
        )

        # Test to_dict conversion
        response_dict = response.to_dict()
        self.assertEqual(response_dict["providers"], ["anthropic", "deepseek"])
        self.assertEqual(response_dict["total_tokens"], 5000)
        self.assertEqual(response_dict["total_cost"], 0.05)
        self.assertTrue(response_dict["success"])

    def test_strategy_enum(self):
        """Test MultiAgentStrategy enum."""
        self.assertEqual(MultiAgentStrategy.ALL.value, "all")
        self.assertEqual(MultiAgentStrategy.SEQUENTIAL.value, "sequential")
        self.assertEqual(MultiAgentStrategy.DIALECTICAL.value, "dialectical")


if __name__ == '__main__':
    unittest.main()
