"""Caching system for LLM responses, GitHub API, and analysis results.

Implements multi-layer caching with TTL, smart invalidation, and metrics tracking.
"""

import hashlib
import json
import pickle
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .logger import AuditLogger


@dataclass
class CacheEntry:
    """Represents a cache entry with metadata."""

    key: str
    value: Any
    created_at: float
    expires_at: float
    hit_count: int
    last_accessed: float
    size_bytes: int
    tags: List[str]


@dataclass
class CacheMetrics:
    """Cache performance metrics."""

    total_hits: int
    total_misses: int
    hit_rate: float
    total_entries: int
    total_size_bytes: int
    avg_entry_size: float
    cache_type: str


class CacheManager:
    """Multi-layer cache manager with TTL and smart invalidation.

    Responsibilities:
    - Store and retrieve cached data
    - Manage TTL and expiration
    - Track cache hits/misses
    - Smart invalidation by tags
    - Compression for large entries
    - Metrics and statistics
    """

    def __init__(
        self,
        cache_dir: Path,
        logger: AuditLogger,
        max_size_mb: int = 1000,
        cleanup_interval: int = 3600,
    ):
        """Initialize cache manager.

        Args:
            cache_dir: Directory for cache storage
            logger: Audit logger instance
            max_size_mb: Maximum cache size in MB
            cleanup_interval: Cleanup interval in seconds
        """
        self.cache_dir = cache_dir
        self.logger = logger
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.cleanup_interval = cleanup_interval
        self.last_cleanup = time.time()

        # In-memory cache
        self._cache: Dict[str, CacheEntry] = {}

        # Metrics
        self._hits = 0
        self._misses = 0

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Load existing cache from disk
        self._load_cache_index()

    def get(self, key: str, default: Optional[Any] = None) -> Optional[Any]:
        """Get value from cache.

        Args:
            key: Cache key
            default: Default value if not found

        Returns:
            Cached value or default
        """
        # Check if cleanup needed
        self._maybe_cleanup()

        # Check in-memory cache
        if key in self._cache:
            entry = self._cache[key]

            # Check if expired
            if time.time() > entry.expires_at:
                self._delete(key)
                self._misses += 1
                self.logger.debug("cache_miss", key=key, reason="expired")
                return default

            # Update access stats
            entry.hit_count += 1
            entry.last_accessed = time.time()
            self._hits += 1

            self.logger.debug(
                "cache_hit",
                key=key,
                hit_count=entry.hit_count,
                age_seconds=time.time() - entry.created_at,
            )

            return entry.value

        self._misses += 1
        self.logger.debug("cache_miss", key=key, reason="not_found")
        return default

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int = 86400,
        tags: Optional[List[str]] = None,
    ):
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time to live in seconds
            tags: Tags for invalidation
        """
        now = time.time()
        expires_at = now + ttl_seconds

        # Calculate size
        size_bytes = len(pickle.dumps(value))

        # Check if we need to evict
        self._maybe_evict(size_bytes)

        # Create entry
        entry = CacheEntry(
            key=key,
            value=value,
            created_at=now,
            expires_at=expires_at,
            hit_count=0,
            last_accessed=now,
            size_bytes=size_bytes,
            tags=tags or [],
        )

        # Store in memory
        self._cache[key] = entry

        # Persist to disk
        self._persist_entry(entry)

        self.logger.debug(
            "cache_set",
            key=key,
            ttl_seconds=ttl_seconds,
            size_bytes=size_bytes,
            tags=tags,
        )

    def delete(self, key: str):
        """Delete entry from cache.

        Args:
            key: Cache key
        """
        self._delete(key)
        self.logger.debug("cache_delete", key=key)

    def invalidate_by_tags(self, tags: List[str]):
        """Invalidate all entries matching tags.

        Args:
            tags: Tags to match
        """
        keys_to_delete = []
        for key, entry in self._cache.items():
            if any(tag in entry.tags for tag in tags):
                keys_to_delete.append(key)

        for key in keys_to_delete:
            self._delete(key)

        self.logger.info(
            "cache_invalidated_by_tags",
            tags=tags,
            entries_deleted=len(keys_to_delete),
        )

    def clear(self):
        """Clear entire cache."""
        count = len(self._cache)
        self._cache.clear()

        # Clear disk cache
        for cache_file in self.cache_dir.glob("*.cache"):
            cache_file.unlink()

        self.logger.info("cache_cleared", entries_deleted=count)

    def get_metrics(self, cache_type: str = "general") -> CacheMetrics:
        """Get cache metrics.

        Args:
            cache_type: Type of cache for metrics

        Returns:
            CacheMetrics with statistics
        """
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0.0

        total_size = sum(entry.size_bytes for entry in self._cache.values())
        avg_size = total_size / len(self._cache) if self._cache else 0.0

        return CacheMetrics(
            total_hits=self._hits,
            total_misses=self._misses,
            hit_rate=hit_rate,
            total_entries=len(self._cache),
            total_size_bytes=total_size,
            avg_entry_size=avg_size,
            cache_type=cache_type,
        )

    def _delete(self, key: str):
        """Delete entry from cache and disk.

        Args:
            key: Cache key
        """
        if key in self._cache:
            del self._cache[key]

        # Delete from disk
        cache_file = self._get_cache_file(key)
        if cache_file.exists():
            cache_file.unlink()

    def _maybe_cleanup(self):
        """Cleanup expired entries if needed."""
        now = time.time()
        if now - self.last_cleanup < self.cleanup_interval:
            return

        expired_keys = []
        for key, entry in self._cache.items():
            if now > entry.expires_at:
                expired_keys.append(key)

        for key in expired_keys:
            self._delete(key)

        self.last_cleanup = now
        if expired_keys:
            self.logger.info("cache_cleanup", entries_removed=len(expired_keys))

    def _maybe_evict(self, needed_bytes: int):
        """Evict entries if needed to make space.

        Args:
            needed_bytes: Bytes needed for new entry
        """
        current_size = sum(entry.size_bytes for entry in self._cache.values())

        if current_size + needed_bytes <= self.max_size_bytes:
            return

        # Evict LRU entries until we have space
        entries_by_access = sorted(
            self._cache.items(), key=lambda x: x[1].last_accessed
        )

        bytes_freed = 0
        evicted_count = 0

        for key, entry in entries_by_access:
            if current_size + needed_bytes - bytes_freed <= self.max_size_bytes:
                break

            self._delete(key)
            bytes_freed += entry.size_bytes
            evicted_count += 1

        if evicted_count > 0:
            self.logger.info(
                "cache_evicted",
                entries_evicted=evicted_count,
                bytes_freed=bytes_freed,
            )

    def _persist_entry(self, entry: CacheEntry):
        """Persist entry to disk.

        Args:
            entry: Cache entry to persist
        """
        cache_file = self._get_cache_file(entry.key)
        with open(cache_file, "wb") as f:
            pickle.dump(entry, f)

    def _load_cache_index(self):
        """Load cache index from disk."""
        loaded = 0
        for cache_file in self.cache_dir.glob("*.cache"):
            try:
                with open(cache_file, "rb") as f:
                    entry = pickle.load(f)

                # Check if expired
                if time.time() > entry.expires_at:
                    cache_file.unlink()
                    continue

                self._cache[entry.key] = entry
                loaded += 1
            except Exception as e:
                self.logger.warning(
                    "cache_load_failed", file=str(cache_file), error=str(e)
                )
                cache_file.unlink()

        if loaded > 0:
            self.logger.info("cache_loaded", entries=loaded)

    def _get_cache_file(self, key: str) -> Path:
        """Get cache file path for key.

        Args:
            key: Cache key

        Returns:
            Path to cache file
        """
        # Hash key to create safe filename
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        return self.cache_dir / f"{key_hash}.cache"


class LLMCache:
    """Cache for LLM responses."""

    def __init__(self, cache_manager: CacheManager, logger: AuditLogger):
        """Initialize LLM cache.

        Args:
            cache_manager: Underlying cache manager
            logger: Audit logger instance
        """
        self.cache = cache_manager
        self.logger = logger

    def get_cache_key(
        self, prompt: str, model: str, temperature: float, max_tokens: int
    ) -> str:
        """Generate cache key for LLM request.

        Args:
            prompt: Prompt text
            model: Model name
            temperature: Temperature setting
            max_tokens: Max tokens setting

        Returns:
            Cache key string
        """
        # Create deterministic key from parameters
        key_data = {
            "prompt": prompt,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        key_json = json.dumps(key_data, sort_keys=True)
        key_hash = hashlib.sha256(key_json.encode()).hexdigest()
        return f"llm:{key_hash}"

    def get_response(
        self, prompt: str, model: str, temperature: float, max_tokens: int
    ) -> Optional[str]:
        """Get cached LLM response.

        Args:
            prompt: Prompt text
            model: Model name
            temperature: Temperature setting
            max_tokens: Max tokens setting

        Returns:
            Cached response or None
        """
        key = self.get_cache_key(prompt, model, temperature, max_tokens)
        return self.cache.get(key)

    def set_response(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        response: str,
        ttl_seconds: int = 86400,
    ):
        """Cache LLM response.

        Args:
            prompt: Prompt text
            model: Model name
            temperature: Temperature setting
            max_tokens: Max tokens setting
            response: Response text
            ttl_seconds: Time to live
        """
        key = self.get_cache_key(prompt, model, temperature, max_tokens)
        tags = ["llm", f"model:{model}"]
        self.cache.set(key, response, ttl_seconds=ttl_seconds, tags=tags)

    def invalidate_model(self, model: str):
        """Invalidate all cached responses for a model.

        Args:
            model: Model name
        """
        self.cache.invalidate_by_tags([f"model:{model}"])


class GitHubAPICache:
    """Cache for GitHub API responses."""

    def __init__(self, cache_manager: CacheManager, logger: AuditLogger):
        """Initialize GitHub API cache.

        Args:
            cache_manager: Underlying cache manager
            logger: Audit logger instance
        """
        self.cache = cache_manager
        self.logger = logger

    def get_file_content(
        self, repo: str, path: str, ref: str = "main"
    ) -> Optional[str]:
        """Get cached file content.

        Args:
            repo: Repository name
            path: File path
            ref: Git ref

        Returns:
            Cached content or None
        """
        key = f"github:file:{repo}:{path}:{ref}"
        return self.cache.get(key)

    def set_file_content(
        self, repo: str, path: str, ref: str, content: str, ttl_seconds: int = 3600
    ):
        """Cache file content.

        Args:
            repo: Repository name
            path: File path
            ref: Git ref
            content: File content
            ttl_seconds: Time to live
        """
        key = f"github:file:{repo}:{path}:{ref}"
        tags = ["github", f"repo:{repo}", f"ref:{ref}"]
        self.cache.set(key, content, ttl_seconds=ttl_seconds, tags=tags)

    def invalidate_repo(self, repo: str):
        """Invalidate all cached data for a repository.

        Args:
            repo: Repository name
        """
        self.cache.invalidate_by_tags([f"repo:{repo}"])

    def invalidate_ref(self, repo: str, ref: str):
        """Invalidate cached data for a specific ref.

        Args:
            repo: Repository name
            ref: Git ref
        """
        self.cache.invalidate_by_tags([f"repo:{repo}", f"ref:{ref}"])


class AnalysisCache:
    """Cache for codebase analysis results."""

    def __init__(self, cache_manager: CacheManager, logger: AuditLogger):
        """Initialize analysis cache.

        Args:
            cache_manager: Underlying cache manager
            logger: Audit logger instance
        """
        self.cache = cache_manager
        self.logger = logger

    def get_complexity_score(self, file_path: str, commit_sha: str) -> Optional[int]:
        """Get cached complexity score.

        Args:
            file_path: Path to file
            commit_sha: Git commit SHA

        Returns:
            Cached score or None
        """
        key = f"analysis:complexity:{file_path}:{commit_sha}"
        return self.cache.get(key)

    def set_complexity_score(
        self, file_path: str, commit_sha: str, score: int, ttl_seconds: int = 604800
    ):
        """Cache complexity score.

        Args:
            file_path: Path to file
            commit_sha: Git commit SHA
            score: Complexity score
            ttl_seconds: Time to live (default 7 days)
        """
        key = f"analysis:complexity:{file_path}:{commit_sha}"
        tags = ["analysis", "complexity", f"file:{file_path}"]
        self.cache.set(key, score, ttl_seconds=ttl_seconds, tags=tags)

    def get_codebase_analysis(
        self, repo: str, commit_sha: str
    ) -> Optional[Dict[str, Any]]:
        """Get cached codebase analysis.

        Args:
            repo: Repository name
            commit_sha: Git commit SHA

        Returns:
            Cached analysis or None
        """
        key = f"analysis:codebase:{repo}:{commit_sha}"
        return self.cache.get(key)

    def set_codebase_analysis(
        self,
        repo: str,
        commit_sha: str,
        analysis: Dict[str, Any],
        ttl_seconds: int = 604800,
    ):
        """Cache codebase analysis.

        Args:
            repo: Repository name
            commit_sha: Git commit SHA
            analysis: Analysis results
            ttl_seconds: Time to live (default 7 days)
        """
        key = f"analysis:codebase:{repo}:{commit_sha}"
        tags = ["analysis", "codebase", f"repo:{repo}"]
        self.cache.set(key, analysis, ttl_seconds=ttl_seconds, tags=tags)

    def invalidate_file(self, file_path: str):
        """Invalidate all cached analysis for a file.

        Args:
            file_path: Path to file
        """
        self.cache.invalidate_by_tags([f"file:{file_path}"])
