"""API key rotation and failover for LLM providers.

Supports multiple API keys per provider with automatic rotation on rate
limits (429) and auth failures (401/402). Keys cool down after failures
before being retried.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Cooldown durations by HTTP status code
_COOLDOWN_SECONDS: dict[int, float] = {
    429: 30.0,  # Rate limit: cool down 30s
    401: 300.0,  # Unauthorized: cool down 5min
    402: 300.0,  # Payment required: cool down 5min
    403: 600.0,  # Forbidden: cool down 10min
    500: 60.0,  # Server error: cool down 1min
    502: 30.0,  # Bad gateway: cool down 30s
    503: 60.0,  # Service unavailable: cool down 1min
}


@dataclass
class AuthProfile:
    """A single API key with usage tracking."""

    key: str
    provider: str = ""
    failed_at: float = 0.0
    failure_status: int = 0
    cooldown_until: float = 0.0
    request_count: int = 0
    failure_count: int = 0

    @property
    def is_available(self) -> bool:
        """Check if this profile is available (not in cooldown)."""
        if self.cooldown_until <= 0:
            return True
        return time.time() >= self.cooldown_until

    def mark_success(self) -> None:
        """Record a successful request."""
        self.request_count += 1
        # Reset failure state on success
        self.failed_at = 0.0
        self.failure_status = 0
        self.cooldown_until = 0.0

    def mark_failure(self, status_code: int) -> None:
        """Record a failed request and set cooldown."""
        self.failure_count += 1
        self.failed_at = time.time()
        self.failure_status = status_code
        cooldown = _COOLDOWN_SECONDS.get(status_code, 60.0)
        self.cooldown_until = time.time() + cooldown
        logger.warning(
            "Auth profile %s...%s failed with %d, cooling down for %.0fs",
            self.key[:8],
            self.key[-4:],
            status_code,
            cooldown,
        )


class AuthProfileManager:
    """Manages multiple API keys per provider with rotation and failover.

    Usage:
        manager = AuthProfileManager.from_env("openai")
        key = manager.get_active_key()
        try:
            response = make_request(key)
            manager.mark_success()
        except APIError as e:
            manager.mark_failure(e.status_code)
            key = manager.get_active_key()  # Rotates to next available
    """

    def __init__(self, provider: str, keys: list[str]) -> None:
        """Initialize with provider name and list of API keys.

        Args:
            provider: Provider identifier (e.g., "openai", "anthropic")
            keys: List of API keys to rotate through
        """
        self._provider = provider
        self._profiles = [AuthProfile(key=k, provider=provider) for k in keys if k]
        self._current_index = 0

        if not self._profiles:
            logger.warning("No API keys configured for provider '%s'", provider)

    @classmethod
    def from_env(cls, provider: str) -> "AuthProfileManager":
        """Create from environment variables.

        Looks for:
        - {PROVIDER}_API_KEY (primary)
        - {PROVIDER}_API_KEY_2, {PROVIDER}_API_KEY_3, etc. (additional)

        Args:
            provider: Provider name (e.g., "openai" -> OPENAI_API_KEY)
        """
        prefix = provider.upper().replace("-", "_")
        keys: list[str] = []

        # Primary key
        primary = os.environ.get(f"{prefix}_API_KEY", "")
        if primary:
            keys.append(primary)

        # Additional keys: _2, _3, etc.
        for i in range(2, 10):
            key = os.environ.get(f"{prefix}_API_KEY_{i}", "")
            if key:
                keys.append(key)
            else:
                break

        return cls(provider=provider, keys=keys)

    @classmethod
    def from_config(cls, provider: str, config: dict[str, Any]) -> "AuthProfileManager":
        """Create from configuration dict.

        Args:
            provider: Provider name
            config: Dict with "api_keys" list or "api_key" string
        """
        keys = config.get("api_keys", [])
        if not keys:
            single = config.get("api_key", "")
            if single:
                keys = [single]
        return cls(provider=provider, keys=keys)

    def get_active_key(self) -> Optional[str]:
        """Get the current active API key, rotating if needed.

        Returns:
            An available API key, or None if all keys are in cooldown.
        """
        if not self._profiles:
            return None

        # Try current profile first
        profile = self._profiles[self._current_index]
        if profile.is_available:
            return profile.key

        # Rotate through other profiles
        for i in range(len(self._profiles)):
            idx = (self._current_index + i + 1) % len(self._profiles)
            profile = self._profiles[idx]
            if profile.is_available:
                self._current_index = idx
                logger.info(
                    "Rotated to API key %s...%s for %s",
                    profile.key[:8],
                    profile.key[-4:],
                    self._provider,
                )
                return profile.key

        # All keys in cooldown -- find the one that expires soonest
        soonest = min(self._profiles, key=lambda p: p.cooldown_until)
        wait_time = soonest.cooldown_until - time.time()
        logger.warning(
            "All %d API keys for %s are in cooldown. Nearest available in %.0fs",
            len(self._profiles),
            self._provider,
            max(0, wait_time),
        )
        return None

    def mark_success(self) -> None:
        """Mark the current key as successful."""
        if self._profiles:
            self._profiles[self._current_index].mark_success()

    def mark_failure(self, status_code: int) -> None:
        """Mark the current key as failed with a specific HTTP status code."""
        if self._profiles:
            self._profiles[self._current_index].mark_failure(status_code)

    @property
    def profile_count(self) -> int:
        """Number of configured profiles."""
        return len(self._profiles)

    @property
    def available_count(self) -> int:
        """Number of currently available profiles."""
        return sum(1 for p in self._profiles if p.is_available)

    def get_stats(self) -> dict[str, Any]:
        """Get usage statistics for all profiles."""
        return {
            "provider": self._provider,
            "total_profiles": len(self._profiles),
            "available": self.available_count,
            "current_index": self._current_index,
            "profiles": [
                {
                    "key_prefix": f"{p.key[:8]}...{p.key[-4:]}",
                    "available": p.is_available,
                    "requests": p.request_count,
                    "failures": p.failure_count,
                    "last_failure_status": p.failure_status or None,
                    "cooldown_remaining": max(0, p.cooldown_until - time.time()),
                }
                for p in self._profiles
            ],
        }
