"""Unit tests for caching system."""

import tempfile
import time
from pathlib import Path

import pytest

from src.core.cache import (
    AnalysisCache,
    CacheManager,
    GitHubAPICache,
    LLMCache,
)
from src.core.logger import setup_logging


@pytest.fixture
def temp_cache_dir():
    """Create temporary cache directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def logger():
    """Create logger."""
    return setup_logging()


@pytest.fixture
def cache_manager(temp_cache_dir, logger):
    """Create cache manager."""
    return CacheManager(
        cache_dir=temp_cache_dir, logger=logger, max_size_mb=10, cleanup_interval=1
    )


class TestCacheManager:
    """Tests for CacheManager."""

    def test_set_and_get(self, cache_manager):
        """Test basic set and get operations."""
        cache_manager.set("key1", "value1", ttl_seconds=60)
        assert cache_manager.get("key1") == "value1"

    def test_get_missing_key(self, cache_manager):
        """Test getting missing key returns default."""
        assert cache_manager.get("missing") is None
        assert cache_manager.get("missing", default="default") == "default"

    def test_ttl_expiration(self, cache_manager):
        """Test TTL expiration."""
        cache_manager.set("expiring", "value", ttl_seconds=1)
        assert cache_manager.get("expiring") == "value"

        # Wait for expiration
        time.sleep(1.1)
        assert cache_manager.get("expiring") is None

    def test_delete(self, cache_manager):
        """Test deletion."""
        cache_manager.set("to_delete", "value")
        assert cache_manager.get("to_delete") == "value"

        cache_manager.delete("to_delete")
        assert cache_manager.get("to_delete") is None

    def test_tags(self, cache_manager):
        """Test tagging and tag-based invalidation."""
        cache_manager.set("item1", "value1", tags=["tag1", "tag2"])
        cache_manager.set("item2", "value2", tags=["tag2", "tag3"])
        cache_manager.set("item3", "value3", tags=["tag3"])

        # Invalidate by tag2
        cache_manager.invalidate_by_tags(["tag2"])

        # item1 and item2 should be gone
        assert cache_manager.get("item1") is None
        assert cache_manager.get("item2") is None
        # item3 should remain
        assert cache_manager.get("item3") == "value3"

    def test_clear(self, cache_manager):
        """Test clearing entire cache."""
        cache_manager.set("key1", "value1")
        cache_manager.set("key2", "value2")
        cache_manager.set("key3", "value3")

        assert len(cache_manager._cache) == 3

        cache_manager.clear()
        assert len(cache_manager._cache) == 0
        assert cache_manager.get("key1") is None

    def test_hit_count(self, cache_manager):
        """Test hit count tracking."""
        cache_manager.set("key", "value")

        # First access
        cache_manager.get("key")
        entry = cache_manager._cache["key"]
        assert entry.hit_count == 1

        # Second access
        cache_manager.get("key")
        assert entry.hit_count == 2

    def test_metrics(self, cache_manager):
        """Test metrics collection."""
        # Add some entries
        cache_manager.set("key1", "value1")
        cache_manager.set("key2", "value2")

        # Cause hits and misses
        cache_manager.get("key1")  # Hit
        cache_manager.get("key2")  # Hit
        cache_manager.get("missing")  # Miss

        metrics = cache_manager.get_metrics("test")

        assert metrics.total_hits == 2
        assert metrics.total_misses == 1
        assert metrics.hit_rate == 2 / 3
        assert metrics.total_entries == 2

    def test_eviction(self, temp_cache_dir, logger):
        """Test LRU eviction when cache is full."""
        # Create small cache (1 KB)
        manager = CacheManager(
            cache_dir=temp_cache_dir, logger=logger, max_size_mb=0.001
        )

        # Add entries
        manager.set("key1", "a" * 500)  # 500 bytes
        manager.set("key2", "b" * 500)  # 500 bytes
        manager.set("key3", "c" * 500)  # 500 bytes - should trigger eviction

        # key1 should be evicted (LRU)
        assert manager.get("key1") is None
        assert manager.get("key2") == "b" * 500
        assert manager.get("key3") == "c" * 500

    def test_persistence(self, temp_cache_dir, logger):
        """Test cache persistence across restarts."""
        # Create cache and add entries
        manager1 = CacheManager(cache_dir=temp_cache_dir, logger=logger)
        manager1.set("persisted", "value", ttl_seconds=3600)

        # Create new manager with same directory
        manager2 = CacheManager(cache_dir=temp_cache_dir, logger=logger)
        assert manager2.get("persisted") == "value"

    def test_cleanup(self, temp_cache_dir, logger):
        """Test periodic cleanup of expired entries."""
        manager = CacheManager(
            cache_dir=temp_cache_dir, logger=logger, cleanup_interval=1
        )

        # Add short-lived entries
        manager.set("short1", "value1", ttl_seconds=1)
        manager.set("short2", "value2", ttl_seconds=1)
        manager.set("long", "value3", ttl_seconds=3600)

        # Wait for expiration
        time.sleep(1.1)

        # Trigger cleanup by accessing cache
        manager._maybe_cleanup()

        # Expired entries should be removed
        assert manager.get("short1") is None
        assert manager.get("short2") is None
        assert manager.get("long") == "value3"


class TestLLMCache:
    """Tests for LLMCache."""

    def test_cache_key_generation(self, cache_manager, logger):
        """Test LLM cache key generation."""
        llm_cache = LLMCache(cache_manager, logger)

        key1 = llm_cache.get_cache_key("prompt", "model", 0.7, 1000)
        key2 = llm_cache.get_cache_key("prompt", "model", 0.7, 1000)
        key3 = llm_cache.get_cache_key("different", "model", 0.7, 1000)

        # Same inputs should produce same key
        assert key1 == key2
        # Different inputs should produce different key
        assert key1 != key3

    def test_get_and_set_response(self, cache_manager, logger):
        """Test caching LLM responses."""
        llm_cache = LLMCache(cache_manager, logger)

        # No cached response initially
        assert llm_cache.get_response("prompt", "model", 0.7, 1000) is None

        # Cache response
        llm_cache.set_response("prompt", "model", 0.7, 1000, "response text")

        # Should retrieve cached response
        cached = llm_cache.get_response("prompt", "model", 0.7, 1000)
        assert cached == "response text"

    def test_invalidate_model(self, cache_manager, logger):
        """Test invalidating all responses for a model."""
        llm_cache = LLMCache(cache_manager, logger)

        # Cache responses for different models
        llm_cache.set_response("prompt1", "model1", 0.7, 1000, "response1")
        llm_cache.set_response("prompt2", "model1", 0.7, 1000, "response2")
        llm_cache.set_response("prompt3", "model2", 0.7, 1000, "response3")

        # Invalidate model1
        llm_cache.invalidate_model("model1")

        # model1 responses should be gone
        assert llm_cache.get_response("prompt1", "model1", 0.7, 1000) is None
        assert llm_cache.get_response("prompt2", "model1", 0.7, 1000) is None
        # model2 response should remain
        assert llm_cache.get_response("prompt3", "model2", 0.7, 1000) == "response3"


class TestGitHubAPICache:
    """Tests for GitHubAPICache."""

    def test_file_content_caching(self, cache_manager, logger):
        """Test caching file contents."""
        gh_cache = GitHubAPICache(cache_manager, logger)

        # No cached content initially
        assert gh_cache.get_file_content("repo", "path/to/file.py", "main") is None

        # Cache content
        gh_cache.set_file_content(
            "repo", "path/to/file.py", "main", "file contents", ttl_seconds=3600
        )

        # Should retrieve cached content
        cached = gh_cache.get_file_content("repo", "path/to/file.py", "main")
        assert cached == "file contents"

    def test_invalidate_repo(self, cache_manager, logger):
        """Test invalidating all cached data for a repository."""
        gh_cache = GitHubAPICache(cache_manager, logger)

        # Cache content for different repos
        gh_cache.set_file_content("repo1", "file1.py", "main", "content1")
        gh_cache.set_file_content("repo1", "file2.py", "main", "content2")
        gh_cache.set_file_content("repo2", "file3.py", "main", "content3")

        # Invalidate repo1
        gh_cache.invalidate_repo("repo1")

        # repo1 content should be gone
        assert gh_cache.get_file_content("repo1", "file1.py", "main") is None
        assert gh_cache.get_file_content("repo1", "file2.py", "main") is None
        # repo2 content should remain
        assert gh_cache.get_file_content("repo2", "file3.py", "main") == "content3"

    def test_invalidate_ref(self, cache_manager, logger):
        """Test invalidating cached data for a specific ref."""
        gh_cache = GitHubAPICache(cache_manager, logger)

        # Cache content for different refs
        gh_cache.set_file_content("repo", "file1.py", "main", "main content 1")
        gh_cache.set_file_content("repo", "file2.py", "main", "main content 2")
        gh_cache.set_file_content("repo", "file3.py", "develop", "develop content")

        # Invalidate main ref on repo
        gh_cache.invalidate_ref("repo", "main")

        # repo main content should be gone
        assert gh_cache.get_file_content("repo", "file1.py", "main") is None
        assert gh_cache.get_file_content("repo", "file2.py", "main") is None
        # develop content should also be gone (shares repo tag with main)
        assert gh_cache.get_file_content("repo", "file3.py", "develop") is None


class TestAnalysisCache:
    """Tests for AnalysisCache."""

    def test_complexity_score_caching(self, cache_manager, logger):
        """Test caching complexity scores."""
        analysis_cache = AnalysisCache(cache_manager, logger)

        # No cached score initially
        assert analysis_cache.get_complexity_score("file.py", "abc123") is None

        # Cache score
        analysis_cache.set_complexity_score("file.py", "abc123", 7)

        # Should retrieve cached score
        cached = analysis_cache.get_complexity_score("file.py", "abc123")
        assert cached == 7

    def test_codebase_analysis_caching(self, cache_manager, logger):
        """Test caching codebase analysis."""
        analysis_cache = AnalysisCache(cache_manager, logger)

        analysis_data = {
            "total_files": 100,
            "complexity_avg": 5.5,
            "patterns": ["factory", "singleton"],
        }

        # No cached analysis initially
        assert analysis_cache.get_codebase_analysis("repo", "abc123") is None

        # Cache analysis
        analysis_cache.set_codebase_analysis("repo", "abc123", analysis_data)

        # Should retrieve cached analysis
        cached = analysis_cache.get_codebase_analysis("repo", "abc123")
        assert cached == analysis_data

    def test_invalidate_file(self, cache_manager, logger):
        """Test invalidating all cached analysis for a file."""
        analysis_cache = AnalysisCache(cache_manager, logger)

        # Cache complexity for different files
        analysis_cache.set_complexity_score("file1.py", "abc123", 5)
        analysis_cache.set_complexity_score("file1.py", "def456", 6)
        analysis_cache.set_complexity_score("file2.py", "abc123", 7)

        # Invalidate file1.py
        analysis_cache.invalidate_file("file1.py")

        # file1.py scores should be gone
        assert analysis_cache.get_complexity_score("file1.py", "abc123") is None
        assert analysis_cache.get_complexity_score("file1.py", "def456") is None
        # file2.py score should remain
        assert analysis_cache.get_complexity_score("file2.py", "abc123") == 7


class TestCacheIntegration:
    """Integration tests for caching system."""

    def test_full_workflow(self, cache_manager, logger):
        """Test complete caching workflow."""
        # Create specialized caches
        llm_cache = LLMCache(cache_manager, logger)
        gh_cache = GitHubAPICache(cache_manager, logger)
        analysis_cache = AnalysisCache(cache_manager, logger)

        # Cache LLM response
        llm_cache.set_response(
            "analyze this code", "claude", 0.7, 1000, "analysis result"
        )

        # Cache GitHub file
        gh_cache.set_file_content("myrepo", "src/main.py", "main", "def main(): pass")

        # Cache analysis
        analysis_cache.set_complexity_score("src/main.py", "commit123", 3)

        # Verify all cached
        assert (
            llm_cache.get_response("analyze this code", "claude", 0.7, 1000)
            == "analysis result"
        )
        assert (
            gh_cache.get_file_content("myrepo", "src/main.py", "main")
            == "def main(): pass"
        )
        assert analysis_cache.get_complexity_score("src/main.py", "commit123") == 3

        # Get metrics
        metrics = cache_manager.get_metrics("integration")
        assert metrics.total_entries == 3
        assert metrics.total_hits > 0

    def test_cache_invalidation_workflow(self, cache_manager, logger):
        """Test cache invalidation workflow."""
        gh_cache = GitHubAPICache(cache_manager, logger)
        analysis_cache = AnalysisCache(cache_manager, logger)

        # Cache file content and analysis
        gh_cache.set_file_content("repo", "file.py", "main", "old content")
        analysis_cache.set_complexity_score("file.py", "old_commit", 5)

        # Simulate code change - invalidate caches
        gh_cache.invalidate_ref("repo", "main")
        analysis_cache.invalidate_file("file.py")

        # Caches should be empty
        assert gh_cache.get_file_content("repo", "file.py", "main") is None
        assert analysis_cache.get_complexity_score("file.py", "old_commit") is None

        # Cache new versions
        gh_cache.set_file_content("repo", "file.py", "main", "new content")
        analysis_cache.set_complexity_score("file.py", "new_commit", 6)

        # Should retrieve new versions
        assert gh_cache.get_file_content("repo", "file.py", "main") == "new content"
        assert analysis_cache.get_complexity_score("file.py", "new_commit") == 6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
