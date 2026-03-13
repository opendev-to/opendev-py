"""Secure credential storage with restrictive file permissions."""

from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class CredentialStore:
    """Manages API keys and tokens with secure file storage.

    Credentials are stored in ~/.opendev/auth.json with mode 0600
    (owner read/write only). Environment variables take precedence.
    """

    # Map provider names to environment variable names
    _ENV_VAR_MAP = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "fireworks": "FIREWORKS_API_KEY",
        "google": "GOOGLE_API_KEY",
        "groq": "GROQ_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "deepinfra": "DEEPINFRA_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "azure": "AZURE_OPENAI_API_KEY",
    }

    def __init__(self, auth_path: Optional[Path] = None):
        self._path = auth_path or (Path.home() / ".opendev" / "auth.json")
        self._cache: dict | None = None

    def get_key(self, provider: str) -> str | None:
        """Get API key for a provider.

        Priority: environment variable > stored credential.

        Args:
            provider: Provider name (e.g., "openai", "anthropic").

        Returns:
            API key string or None.
        """
        # Environment variable takes precedence
        env_var = self._ENV_VAR_MAP.get(provider.lower())
        if env_var:
            env_value = os.environ.get(env_var)
            if env_value:
                return env_value

        # Fall back to stored credential
        data = self._load()
        return data.get("keys", {}).get(provider.lower())

    def set_key(self, provider: str, key: str) -> None:
        """Store an API key for a provider.

        Args:
            provider: Provider name.
            key: API key value.
        """
        data = self._load()
        if "keys" not in data:
            data["keys"] = {}
        data["keys"][provider.lower()] = key
        self._save(data)
        logger.info("Stored API key for %s", provider)

    def remove_key(self, provider: str) -> bool:
        """Remove a stored API key.

        Args:
            provider: Provider name.

        Returns:
            True if key was found and removed.
        """
        data = self._load()
        if provider.lower() in data.get("keys", {}):
            del data["keys"][provider.lower()]
            self._save(data)
            return True
        return False

    def list_providers(self) -> list[dict]:
        """List all providers with key status.

        Returns:
            List of dicts with provider, has_env_key, has_stored_key.
        """
        data = self._load()
        stored_keys = data.get("keys", {})

        result = []
        for provider, env_var in self._ENV_VAR_MAP.items():
            result.append(
                {
                    "provider": provider,
                    "has_env_key": bool(os.environ.get(env_var)),
                    "has_stored_key": provider in stored_keys,
                    "env_var": env_var,
                }
            )
        return result

    def store_token(self, name: str, token: str, metadata: dict | None = None) -> None:
        """Store an arbitrary token (e.g., OAuth token for MCP servers).

        Args:
            name: Token identifier.
            token: Token value.
            metadata: Optional metadata (expiry, scope, etc.).
        """
        data = self._load()
        if "tokens" not in data:
            data["tokens"] = {}
        entry: dict = {"token": token}
        if metadata:
            entry["metadata"] = metadata
        data["tokens"][name] = entry
        self._save(data)

    def get_token(self, name: str) -> str | None:
        """Retrieve a stored token."""
        data = self._load()
        entry = data.get("tokens", {}).get(name)
        if entry:
            return entry.get("token") if isinstance(entry, dict) else entry
        return None

    def _load(self) -> dict:
        """Load credentials from file."""
        if self._cache is not None:
            return self._cache

        if not self._path.exists():
            self._cache = {}
            return self._cache

        try:
            # Verify permissions
            mode = self._path.stat().st_mode
            if mode & (stat.S_IRGRP | stat.S_IROTH):
                logger.warning(
                    "Credential file %s has loose permissions (mode %o). "
                    "Tightening to 0600.",
                    self._path,
                    mode & 0o777,
                )
                os.chmod(self._path, 0o600)

            self._cache = json.loads(self._path.read_text())
            return self._cache
        except Exception:
            logger.warning("Failed to load credentials", exc_info=True)
            self._cache = {}
            return self._cache

    def _save(self, data: dict) -> None:
        """Save credentials to file with restrictive permissions."""
        self._cache = data
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)

            # Write to temp file first, then rename (atomic)
            tmp_path = self._path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(data, indent=2))
            os.chmod(tmp_path, 0o600)
            tmp_path.rename(self._path)
        except Exception:
            logger.warning("Failed to save credentials", exc_info=True)
