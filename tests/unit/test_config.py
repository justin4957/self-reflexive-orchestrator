"""Tests for configuration management."""

import pytest
import tempfile
from pathlib import Path
import yaml

from src.core.config import Config, ConfigManager, OrchestratorConfig


class TestConfig:
    """Test configuration dataclasses."""

    def test_config_defaults(self):
        """Test default configuration values."""
        config = Config()
        assert config.orchestrator.mode == "supervised"
        assert config.orchestrator.poll_interval == 300
        assert config.pr_management.merge_strategy == "squash"

    def test_config_from_dict(self):
        """Test creating config from dictionary."""
        data = {
            "orchestrator": {"mode": "manual", "poll_interval": 600},
            "github": {"repository": "owner/repo", "token": "test-token"},
        }
        config = Config.from_dict(data)

        assert config.orchestrator.mode == "manual"
        assert config.orchestrator.poll_interval == 600
        assert config.github.repository == "owner/repo"
        assert config.github.token == "test-token"

    def test_config_validation_success(self):
        """Test configuration validation with valid config."""
        config = Config()
        config.github.repository = "owner/repo"
        config.github.token = "test-token"
        config.llm.api_key = "test-api-key"

        errors = config.validate()
        assert len(errors) == 0

    def test_config_validation_missing_repository(self):
        """Test validation catches missing repository."""
        config = Config()
        config.github.token = "test-token"
        config.llm.api_key = "test-api-key"

        errors = config.validate()
        assert any("repository is required" in e for e in errors)

    def test_config_validation_invalid_mode(self):
        """Test validation catches invalid mode."""
        config = Config()
        config.orchestrator.mode = "invalid"
        config.github.repository = "owner/repo"
        config.github.token = "test-token"
        config.llm.api_key = "test-api-key"

        errors = config.validate()
        assert any("Invalid mode" in e for e in errors)

    def test_config_validation_invalid_merge_strategy(self):
        """Test validation catches invalid merge strategy."""
        config = Config()
        config.github.repository = "owner/repo"
        config.github.token = "test-token"
        config.llm.api_key = "test-api-key"
        config.pr_management.merge_strategy = "invalid"

        errors = config.validate()
        assert any("Invalid merge strategy" in e for e in errors)


class TestConfigManager:
    """Test configuration manager."""

    def test_load_config_from_file(self):
        """Test loading configuration from YAML file."""
        # Create temporary config file
        config_data = {
            "orchestrator": {"mode": "autonomous", "poll_interval": 120},
            "github": {"repository": "test/repo", "token": "token123"},
            "llm": {"api_key": "llm-key"},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = ConfigManager(config_path)
            config = manager.load()

            assert config.orchestrator.mode == "autonomous"
            assert config.orchestrator.poll_interval == 120
            assert config.github.repository == "test/repo"
            assert config.github.token == "token123"
        finally:
            Path(config_path).unlink()

    def test_config_manager_file_not_found(self):
        """Test error when config file not found."""
        with pytest.raises(FileNotFoundError):
            manager = ConfigManager()
            manager.load()

    def test_config_manager_invalid_config(self):
        """Test error with invalid configuration."""
        # Create temporary config file with missing required fields
        config_data = {
            "orchestrator": {"mode": "autonomous"},
            # Missing github.repository and llm.api_key
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = ConfigManager(config_path)
            with pytest.raises(ValueError):
                manager.load()
        finally:
            Path(config_path).unlink()
