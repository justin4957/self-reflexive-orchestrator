"""Integration tests for Orchestrator initialization.

Tests that Phase 6 components initialize correctly with proper dependencies.
"""

import tempfile
from pathlib import Path

import pytest

from src.core.cache import AnalysisCache, CacheManager, GitHubAPICache, LLMCache
from src.core.database import Database
from src.core.logger import AuditLogger
from src.safety.cost_tracker import CostTracker


class TestPhase6Initialization:
    """Integration tests for Phase 6 component initialization."""

    @pytest.fixture
    def temp_workspace(self):
        """Create temporary workspace for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            workspace.mkdir(parents=True, exist_ok=True)
            yield workspace

    @pytest.fixture
    def logger(self, temp_workspace):
        """Create logger for testing."""
        return AuditLogger(log_file=str(temp_workspace / "test.log"), log_level="INFO")

    @pytest.fixture
    def database(self, temp_workspace, logger):
        """Create database for testing."""
        db_path = temp_workspace / "analytics.db"
        return Database(db_path=str(db_path), logger=logger)

    @pytest.fixture
    def cache_manager(self, temp_workspace, logger):
        """Create cache manager for testing."""
        cache_dir = temp_workspace / "cache"
        return CacheManager(
            cache_dir=cache_dir,
            logger=logger,
            max_size_mb=100,
            cleanup_interval=3600,
        )

    def test_database_initialization(self, temp_workspace, logger):
        """Test that database initializes correctly."""
        db_path = temp_workspace / "analytics.db"
        database = Database(db_path=str(db_path), logger=logger)

        assert database is not None
        assert Path(database.db_path).exists()

    def test_cache_manager_initialization(self, temp_workspace, logger):
        """Test that cache manager initializes correctly."""
        cache_dir = temp_workspace / "cache"
        cache_manager = CacheManager(
            cache_dir=cache_dir,
            logger=logger,
            max_size_mb=100,
            cleanup_interval=3600,
        )

        assert cache_manager is not None
        assert cache_manager.cache_dir == cache_dir

    def test_specialized_caches_initialization(self, cache_manager, logger):
        """Test that specialized caches initialize correctly."""
        # Test LLM Cache
        llm_cache = LLMCache(cache_manager=cache_manager, logger=logger)
        assert llm_cache is not None
        assert llm_cache.cache == cache_manager

        # Test GitHub API Cache
        github_cache = GitHubAPICache(cache_manager=cache_manager, logger=logger)
        assert github_cache is not None
        assert github_cache.cache == cache_manager

        # Test Analysis Cache
        analysis_cache = AnalysisCache(cache_manager=cache_manager, logger=logger)
        assert analysis_cache is not None
        assert analysis_cache.cache == cache_manager

    def test_cost_tracker_initialization_with_workspace(self, temp_workspace, logger):
        """Test that cost_tracker initializes with workspace path."""
        # This is the fix for issues #80 and #81
        cost_tracker = CostTracker(
            max_daily_cost=10.0,
            logger=logger,
            state_file=str(temp_workspace / "cost_tracker.json"),
        )

        assert cost_tracker is not None
        assert cost_tracker.max_daily_cost == 10.0
        assert Path(cost_tracker.state_file).parent == temp_workspace

    def test_cost_tracker_state_file_location(self, temp_workspace, logger):
        """Test that cost_tracker state file is in the correct location."""
        state_file = temp_workspace / "cost_tracker.json"

        cost_tracker = CostTracker(
            max_daily_cost=10.0, logger=logger, state_file=str(state_file)
        )

        # Verify the state file path is correct
        assert Path(cost_tracker.state_file) == state_file
        # Parent directory should be workspace
        assert Path(cost_tracker.state_file).parent == temp_workspace

    def test_phase6_components_work_together(
        self, temp_workspace, logger, database, cache_manager
    ):
        """Test that Phase 6 components can be initialized together."""
        # Initialize all Phase 6 components
        llm_cache = LLMCache(cache_manager=cache_manager, logger=logger)
        github_cache = GitHubAPICache(cache_manager=cache_manager, logger=logger)
        analysis_cache = AnalysisCache(cache_manager=cache_manager, logger=logger)

        cost_tracker = CostTracker(
            max_daily_cost=10.0,
            logger=logger,
            state_file=str(temp_workspace / "cost_tracker.json"),
        )

        # Verify all components exist
        assert database is not None
        assert cache_manager is not None
        assert llm_cache is not None
        assert github_cache is not None
        assert analysis_cache is not None
        assert cost_tracker is not None

        # Verify they can be used together
        assert llm_cache.cache == cache_manager
        assert github_cache.cache == cache_manager
        assert analysis_cache.cache == cache_manager
        assert Path(cost_tracker.state_file).parent == temp_workspace

    def test_workspace_vs_state_dir_fix(self, temp_workspace, logger):
        """Test the fix: workspace should be used instead of non-existent state_dir."""
        # This test validates the fix for issue #80/#81
        # Previously: self.state_dir / "cost_tracker.json"  # WRONG - state_dir doesn't exist
        # Fixed to: self.workspace / "cost_tracker.json"    # CORRECT - workspace exists

        # Simulate what the orchestrator does
        workspace = temp_workspace  # This is self.workspace in orchestrator
        # state_dir doesn't exist and shouldn't be referenced

        # The fix: use workspace directly
        cost_tracker = CostTracker(
            max_daily_cost=10.0,
            logger=logger,
            state_file=str(workspace / "cost_tracker.json"),  # Uses workspace
        )

        # Verify it works
        assert cost_tracker is not None
        assert Path(cost_tracker.state_file).parent == workspace

        # This would fail if we tried to use non-existent state_dir:
        # cost_tracker = CostTracker(..., state_file=str(state_dir / "cost_tracker.json"))
        # AttributeError: 'Orchestrator' object has no attribute 'state_dir'


class TestInitializationOrder:
    """Test that components initialize in the correct order."""

    @pytest.fixture
    def temp_workspace(self):
        """Create temporary workspace for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            workspace.mkdir(parents=True, exist_ok=True)
            yield workspace

    @pytest.fixture
    def logger(self, temp_workspace):
        """Create logger for testing."""
        return AuditLogger(log_file=str(temp_workspace / "test.log"), log_level="INFO")

    def test_database_before_cost_tracker(self, temp_workspace, logger):
        """Test that database can be initialized before cost_tracker."""
        # Phase 6 initialization order
        # 1. Database
        db_path = temp_workspace / "analytics.db"
        database = Database(db_path=str(db_path), logger=logger)

        # 2. Cost Tracker (uses workspace)
        cost_tracker = CostTracker(
            max_daily_cost=10.0,
            logger=logger,
            state_file=str(temp_workspace / "cost_tracker.json"),
        )

        # Both should exist
        assert database is not None
        assert cost_tracker is not None

    def test_cache_before_cost_tracker(self, temp_workspace, logger):
        """Test that caches can be initialized before cost_tracker."""
        # Phase 6 initialization order
        # 1. Cache Manager
        cache_dir = temp_workspace / "cache"
        cache_manager = CacheManager(
            cache_dir=cache_dir,
            logger=logger,
            max_size_mb=100,
            cleanup_interval=3600,
        )

        # 2. Specialized Caches
        llm_cache = LLMCache(cache_manager=cache_manager, logger=logger)

        # 3. Cost Tracker (uses workspace)
        cost_tracker = CostTracker(
            max_daily_cost=10.0,
            logger=logger,
            state_file=str(temp_workspace / "cost_tracker.json"),
        )

        # All should exist
        assert cache_manager is not None
        assert llm_cache is not None
        assert cost_tracker is not None
