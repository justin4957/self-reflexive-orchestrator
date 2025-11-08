"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def mock_github_token():
    """Mock GitHub token for testing."""
    return "ghp_test_token_1234567890"


@pytest.fixture
def mock_anthropic_key():
    """Mock Anthropic API key for testing."""
    return "sk-ant-test-key-1234567890"


@pytest.fixture
def sample_config_data():
    """Sample configuration data for testing."""
    return {
        "orchestrator": {
            "mode": "supervised",
            "poll_interval": 300,
            "work_dir": "./workspace",
        },
        "github": {
            "repository": "test-owner/test-repo",
            "token": "test-token",
            "base_branch": "main",
        },
        "issue_processing": {
            "auto_claim_labels": ["bot-approved"],
            "ignore_labels": ["wontfix"],
            "max_complexity": 7,
            "require_acceptance_criteria": True,
            "max_concurrent": 2,
        },
        "llm": {
            "api_key": "test-api-key",
            "model": "claude-sonnet-4-5-20250929",
            "max_tokens": 8000,
        },
    }
