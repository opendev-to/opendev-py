"""HTTP client management for multi-provider LLM access."""

from typing import Any

from opendev.core.agents.components import (
    create_http_client,
    create_http_client_for_provider,
)


class HttpClientMixin:
    """Mixin for lazy HTTP client initialization.

    Backing stores use ``_priv_*`` names to avoid Python name-mangling
    issues that arise when double-underscore attributes are defined in
    one class (``MainAgent.__init__``) but accessed via properties in a
    mixin (where the mangled name would differ).
    """

    @property
    def _http_client(self) -> Any:
        """Lazily create HTTP client on first access (defers API key validation)."""
        if self._priv_http_client is None:
            self._priv_http_client = create_http_client(self.config)
        return self._priv_http_client

    @property
    def _thinking_http_client(self) -> Any:
        """Lazily create HTTP client for Thinking model provider.

        Only created if Thinking model is configured with a different provider.
        Returns None if Thinking model uses same provider as Normal model.
        """
        if self._priv_thinking_http_client is None:
            # Only create if thinking provider is different from normal provider
            thinking_provider = self.config.model_thinking_provider
            if thinking_provider and thinking_provider != self.config.model_provider:
                try:
                    self._priv_thinking_http_client = create_http_client_for_provider(
                        thinking_provider, self.config
                    )
                except ValueError:
                    # API key not set - fall back to normal client
                    return self._http_client
        return self._priv_thinking_http_client

    @property
    def _critique_http_client(self) -> Any:
        """Lazily create HTTP client for Critique model provider.

        Only created if Critique model is configured with a different provider.
        Falls back to thinking client, then normal client.
        """
        if self._priv_critique_http_client is None:
            critique_provider = self.config.model_critique_provider
            if critique_provider and critique_provider != self.config.model_provider:
                # Different provider than normal - create dedicated client
                if critique_provider != self.config.model_thinking_provider:
                    # Also different from thinking - create new client
                    try:
                        self._priv_critique_http_client = create_http_client_for_provider(
                            critique_provider, self.config
                        )
                    except ValueError:
                        # API key not set - fall back to thinking or normal client
                        return self._thinking_http_client or self._http_client
                else:
                    # Same as thinking provider - reuse thinking client
                    return self._thinking_http_client or self._http_client
        return self._priv_critique_http_client

    @property
    def _vlm_http_client(self) -> Any:
        """Lazily create HTTP client for VLM model provider.

        Only created if VLM model is configured with a different provider.
        Falls back to normal client on error.
        """
        if self._priv_vlm_http_client is None:
            vlm_provider = self.config.model_vlm_provider
            if vlm_provider and vlm_provider != self.config.model_provider:
                try:
                    self._priv_vlm_http_client = create_http_client_for_provider(
                        vlm_provider, self.config
                    )
                except ValueError:
                    return self._http_client
        return self._priv_vlm_http_client

    def _resolve_vlm_model_and_client(self, messages: list[dict]) -> tuple[str, Any]:
        """Resolve model/client, routing to VLM when images are present."""
        if self._messages_contain_images(messages):
            vlm_info = self.config.get_vlm_model_info()
            if vlm_info is not None:
                _, vlm_model_id, _ = vlm_info
                vlm_provider = self.config.model_vlm_provider
                if vlm_provider and vlm_provider != self.config.model_provider:
                    http_client = self._vlm_http_client or self._http_client
                else:
                    http_client = self._http_client
                return vlm_model_id, http_client
        return self.config.model, self._http_client
