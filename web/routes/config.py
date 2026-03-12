"""Configuration API endpoints."""

from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from opendev.web.state import get_state, broadcast_to_all_clients
from opendev.config import get_model_registry
from opendev.core.runtime.approval.constants import AutonomyLevel, ThinkingLevel
from opendev.core.runtime.mode_manager import OperationMode
from opendev.web.protocol import WSMessageType

router = APIRouter(prefix="/api/config", tags=["config"])


class ConfigUpdate(BaseModel):
    """Configuration update model."""

    model_provider: str | None = None
    model: str | None = None
    model_thinking_provider: str | None = None
    model_thinking: str | None = None
    model_vlm_provider: str | None = None
    model_vlm: str | None = None
    model_critique_provider: str | None = None
    model_critique: str | None = None
    model_compact_provider: str | None = None
    model_compact: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    enable_bash: bool | None = None


@router.get("")
async def get_config() -> Dict[str, Any]:
    """Get current configuration.

    Returns:
        Current configuration (with masked API keys)

    Raises:
        HTTPException: If retrieval fails
    """
    try:
        state = get_state()
        config = state.config_manager.get_config()

        # Mask API key
        api_key = config.api_key
        masked_key = None
        if api_key:
            if len(api_key) > 8:
                masked_key = f"{api_key[:4]}...{api_key[-4:]}"
            else:
                masked_key = "***"

        # Get mode, autonomy, working dir, and git branch
        mode = state.mode_manager.current_mode.value
        autonomy_level = state.get_autonomy_level()
        session = state.session_manager.get_current_session()
        working_dir = session.working_directory if session else ""
        git_branch = state.get_git_branch()

        return {
            "model_provider": config.model_provider,
            "model": config.model,
            "model_thinking_provider": config.model_thinking_provider,
            "model_thinking": config.model_thinking,
            "model_vlm_provider": config.model_vlm_provider,
            "model_vlm": config.model_vlm,
            "model_critique_provider": config.model_critique_provider,
            "model_critique": config.model_critique,
            "model_compact_provider": config.model_compact_provider,
            "model_compact": config.model_compact,
            "api_key": masked_key,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "enable_bash": config.enable_bash,
            "mode": mode,
            "autonomy_level": autonomy_level,
            "thinking_level": state.get_thinking_level(),
            "working_dir": working_dir or "",
            "git_branch": git_branch,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("")
async def update_config(update: ConfigUpdate) -> Dict[str, str]:
    """Update configuration.

    Args:
        update: Configuration updates

    Returns:
        Status response

    Raises:
        HTTPException: If update fails
    """
    try:
        state = get_state()
        config = state.config_manager.get_config()

        # Update fields if provided
        if update.model_provider is not None:
            config.model_provider = update.model_provider
        if update.model is not None:
            config.model = update.model
        if update.model_thinking_provider is not None:
            config.model_thinking_provider = update.model_thinking_provider
        if update.model_thinking is not None:
            config.model_thinking = update.model_thinking
        if update.model_vlm_provider is not None:
            config.model_vlm_provider = update.model_vlm_provider
        if update.model_vlm is not None:
            config.model_vlm = update.model_vlm
        if update.model_critique_provider is not None:
            config.model_critique_provider = update.model_critique_provider
        if update.model_critique is not None:
            config.model_critique = update.model_critique
        if update.model_compact_provider is not None:
            config.model_compact_provider = update.model_compact_provider
        if update.model_compact is not None:
            config.model_compact = update.model_compact
        if update.temperature is not None:
            config.temperature = update.temperature
        if update.max_tokens is not None:
            config.max_tokens = update.max_tokens
        if update.enable_bash is not None:
            config.enable_bash = update.enable_bash
            # Also update permissions.bash.enabled for consistency
            if hasattr(config, "permissions"):
                config.permissions.bash.enabled = update.enable_bash

        # Save configuration with the updated config object
        state.config_manager.save_config(config, global_config=True)

        return {"status": "success", "message": "Configuration updated"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ModeUpdate(BaseModel):
    """Mode update model."""

    mode: str


class AutonomyUpdate(BaseModel):
    """Autonomy update model."""

    level: str


@router.post("/mode")
async def set_mode(update: ModeUpdate) -> Dict[str, str]:
    """Set operation mode (normal/plan).

    Args:
        update: Mode update

    Returns:
        Status response
    """
    try:
        state = get_state()
        mode = OperationMode(update.mode)
        state.mode_manager.set_mode(mode)

        # Broadcast status update to all clients
        session = state.session_manager.get_current_session()
        await broadcast_to_all_clients(
            {
                "type": WSMessageType.STATUS_UPDATE,
                "data": {
                    "mode": mode.value,
                    "autonomy_level": state.get_autonomy_level(),
                    "thinking_level": state.get_thinking_level(),
                    "working_dir": session.working_directory if session else "",
                    "git_branch": state.get_git_branch(),
                },
            }
        )

        return {"status": "success", "message": f"Mode set to {mode.value}"}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {update.mode}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/autonomy")
async def set_autonomy(update: AutonomyUpdate) -> Dict[str, str]:
    """Set autonomy level (Manual/Semi-Auto/Auto).

    Args:
        update: Autonomy update

    Returns:
        Status response
    """
    try:
        valid_levels = {level.value for level in AutonomyLevel}
        if update.level not in valid_levels:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid autonomy level: {update.level}. Must be one of {valid_levels}",
            )

        state = get_state()
        state.set_autonomy_level(update.level)

        # Broadcast status update to all clients
        session = state.session_manager.get_current_session()
        await broadcast_to_all_clients(
            {
                "type": WSMessageType.STATUS_UPDATE,
                "data": {
                    "mode": state.mode_manager.current_mode.value,
                    "autonomy_level": update.level,
                    "thinking_level": state.get_thinking_level(),
                    "working_dir": session.working_directory if session else "",
                    "git_branch": state.get_git_branch(),
                },
            }
        )

        return {"status": "success", "message": f"Autonomy set to {update.level}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ThinkingUpdate(BaseModel):
    """Thinking level update model."""

    level: str


@router.post("/thinking")
async def set_thinking(update: ThinkingUpdate) -> Dict[str, str]:
    """Set thinking level (Off/Low/Medium/High).

    Args:
        update: Thinking level update

    Returns:
        Status response
    """
    try:
        valid_levels = {level.value for level in ThinkingLevel}
        if update.level not in valid_levels:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid thinking level: {update.level}. Must be one of {valid_levels}",
            )

        state = get_state()
        state.set_thinking_level(update.level)

        # Broadcast status update to all clients
        session = state.session_manager.get_current_session()
        await broadcast_to_all_clients(
            {
                "type": WSMessageType.STATUS_UPDATE,
                "data": {
                    "mode": state.mode_manager.current_mode.value,
                    "autonomy_level": state.get_autonomy_level(),
                    "thinking_level": update.level,
                    "working_dir": session.working_directory if session else "",
                    "git_branch": state.get_git_branch(),
                },
            }
        )

        return {"status": "success", "message": f"Thinking level set to {update.level}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class VerifyModelRequest(BaseModel):
    """Request model for verifying a model works."""

    provider: str
    model: str


@router.post("/verify-model")
async def verify_model(request: VerifyModelRequest) -> Dict[str, Any]:
    """Verify that a provider/model combination is accessible.

    Sends a minimal test request (max_tokens=1) to check that:
    - The provider API key is set
    - The model exists and is accessible
    - The provider endpoint is reachable

    Args:
        request: Provider and model to verify

    Returns:
        Dict with 'valid' bool and optional 'error' string
    """
    import asyncio

    try:
        # First check model exists in registry
        registry = get_model_registry()
        provider_info = registry.get_provider(request.provider)
        if not provider_info:
            return {"valid": False, "error": f"Unknown provider: {request.provider}"}

        model_result = registry.find_model_by_id(request.model)
        if not model_result:
            return {"valid": False, "error": f"Unknown model: {request.model}"}

        # Create HTTP client and send minimal test request
        from opendev.core.agents.components.api.configuration import (
            create_http_client_for_provider,
        )

        state = get_state()
        config = state.config_manager.get_config()

        try:
            client = create_http_client_for_provider(request.provider, config)
        except ValueError as e:
            return {"valid": False, "error": str(e)}

        # Build minimal test payload
        payload = {
            "model": request.model,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
        }

        # Convert request if needed (e.g. Anthropic format)
        converted_payload = client.convert_request(payload)

        # Run the blocking HTTP call in a thread pool
        result = await asyncio.to_thread(client.post_json, converted_payload)

        if not result.success:
            return {"valid": False, "error": result.error or "Request failed"}

        if result.response is not None:
            status_code = result.response.status_code
            if status_code >= 400:
                # Try to extract error message from response
                try:
                    error_data = result.response.json()
                    error_msg = (
                        error_data.get("error", {}).get("message")
                        or error_data.get("message")
                        or error_data.get("detail")
                        or f"HTTP {status_code}"
                    )
                except Exception:
                    error_msg = f"HTTP {status_code}"
                return {"valid": False, "error": error_msg}

        return {"valid": True}

    except Exception as e:
        return {"valid": False, "error": f"Verification failed: {str(e)}"}


@router.get("/providers")
async def list_providers() -> List[Dict[str, Any]]:
    """List all available AI providers.

    Returns:
        List of provider information

    Raises:
        HTTPException: If listing fails
    """
    try:
        registry = get_model_registry()
        providers = []

        for provider_info in registry.list_providers():
            # Format models with context info (no pricing)
            models = []
            for model_info in provider_info.list_models():
                description = f"{model_info.context_length//1000}k context"
                if model_info.recommended:
                    description = "Recommended • " + description

                models.append(
                    {
                        "id": model_info.id,
                        "name": model_info.name,
                        "description": description,
                    }
                )

            providers.append(
                {
                    "id": provider_info.id,
                    "name": provider_info.name,
                    "description": provider_info.description,
                    "models": models,
                }
            )

        return providers

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
