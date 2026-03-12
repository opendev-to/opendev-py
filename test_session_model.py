"""Tests for per-session model configuration overlay."""

import pytest
from unittest.mock import MagicMock, patch

from opendev.core.runtime.session_model import (
    SESSION_MODEL_FIELDS,
    SessionModelManager,
    get_session_model,
    set_session_model,
    clear_session_model,
    validate_session_model,
)
from opendev.models.config import AppConfig


@pytest.fixture
def config():
    """Create a base AppConfig for testing."""
    return AppConfig(
        model_provider="fireworks",
        model="accounts/fireworks/models/kimi-k2-instruct-0905",
        model_thinking_provider="openai",
        model_thinking="gpt-4o",
        max_context_tokens=100000,
    )


@pytest.fixture
def session():
    """Create a mock session with metadata dict."""
    s = MagicMock()
    s.metadata = {}
    return s


@pytest.fixture
def manager(config):
    return SessionModelManager(config)


class TestSessionModelManager:
    def test_initial_state(self, manager):
        assert not manager.is_active
        assert manager.get_overlay() is None

    def test_apply_full_overlay(self, manager, config):
        overlay = {
            "model": "gpt-4o",
            "model_provider": "openai",
        }
        manager.apply(overlay)

        assert manager.is_active
        assert config.model == "gpt-4o"
        assert config.model_provider == "openai"
        assert manager.get_overlay() == overlay

    def test_apply_partial_overlay(self, manager, config):
        """Only specified slots change, others untouched."""
        original_thinking = config.model_thinking
        original_thinking_provider = config.model_thinking_provider

        overlay = {
            "model": "gpt-4o",
            "model_provider": "openai",
        }
        manager.apply(overlay)

        assert config.model == "gpt-4o"
        assert config.model_thinking == original_thinking
        assert config.model_thinking_provider == original_thinking_provider

    def test_restore(self, manager, config):
        original_model = config.model
        original_provider = config.model_provider

        overlay = {
            "model": "gpt-4o",
            "model_provider": "openai",
        }
        manager.apply(overlay)
        assert config.model == "gpt-4o"

        manager.restore()
        assert config.model == original_model
        assert config.model_provider == original_provider
        assert not manager.is_active
        assert manager.get_overlay() is None

    def test_apply_ignores_invalid_keys(self, manager, config):
        overlay = {
            "model": "gpt-4o",
            "model_provider": "openai",
            "invalid_key": "should_be_ignored",
        }
        manager.apply(overlay)
        assert config.model == "gpt-4o"
        assert (
            not hasattr(config, "invalid_key")
            or getattr(config, "invalid_key", None) != "should_be_ignored"
        )

    def test_get_overlay_returns_copy(self, manager):
        overlay = {"model": "gpt-4o", "model_provider": "openai"}
        manager.apply(overlay)
        result = manager.get_overlay()
        result["extra"] = "modified"
        assert "extra" not in manager.get_overlay()


class TestSessionMetadataHelpers:
    def test_get_set_clear_roundtrip(self, session):
        assert get_session_model(session) is None

        overlay = {"model": "gpt-4o", "model_provider": "openai"}
        set_session_model(session, overlay)
        assert get_session_model(session) == overlay

        clear_session_model(session)
        assert get_session_model(session) is None

    def test_clear_no_op_when_empty(self, session):
        clear_session_model(session)
        assert "session_model" not in session.metadata


class TestValidateSessionModel:
    @patch("opendev.config.get_model_registry")
    def test_valid_model_kept(self, mock_registry_fn):
        registry = MagicMock()
        mock_registry_fn.return_value = registry
        registry.find_model_by_id.return_value = ("openai", "gpt-4o", MagicMock())

        overlay = {"model": "gpt-4o", "model_provider": "openai"}
        valid, warnings = validate_session_model(overlay)
        assert valid == overlay
        assert warnings == []

    @patch("opendev.config.get_model_registry")
    def test_invalid_model_removed(self, mock_registry_fn):
        registry = MagicMock()
        mock_registry_fn.return_value = registry
        registry.find_model_by_id.return_value = None

        overlay = {"model": "deleted-model", "model_provider": "openai"}
        valid, warnings = validate_session_model(overlay)
        assert valid == {}
        assert len(warnings) == 1
        assert "deleted-model" in warnings[0]

    @patch("opendev.config.get_model_registry")
    def test_mixed_valid_invalid(self, mock_registry_fn):
        registry = MagicMock()
        mock_registry_fn.return_value = registry

        def find_model(model_id):
            if model_id == "gpt-4o":
                return ("openai", "gpt-4o", MagicMock())
            return None

        registry.find_model_by_id.side_effect = find_model

        overlay = {
            "model": "gpt-4o",
            "model_provider": "openai",
            "model_thinking": "deleted-model",
            "model_thinking_provider": "openai",
        }
        valid, warnings = validate_session_model(overlay)
        assert "model" in valid
        assert "model_provider" in valid
        assert "model_thinking" not in valid
        assert len(warnings) == 1

    def test_empty_overlay(self):
        valid, warnings = validate_session_model({})
        assert valid == {}
        assert warnings == []

    def test_none_overlay(self):
        valid, warnings = validate_session_model(None)
        assert valid == {}
        assert warnings == []

    @patch("opendev.config.get_model_registry")
    def test_registry_unavailable_keeps_all(self, mock_registry_fn):
        mock_registry_fn.side_effect = ImportError("no registry")
        overlay = {"model": "anything", "model_provider": "openai"}
        valid, warnings = validate_session_model(overlay)
        assert valid == overlay
        assert warnings == []


class TestSessionModelFields:
    def test_all_fields_are_appconfig_attrs(self):
        config = AppConfig()
        for field in SESSION_MODEL_FIELDS:
            assert hasattr(config, field), f"{field} not found on AppConfig"
