"""Provider-specific schema adaptation.

Different LLM providers have different JSON Schema requirements. This module
applies provider-specific transformations to tool schemas before they are
sent to the LLM.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)


def adapt_for_provider(
    schemas: list[dict[str, Any]],
    provider: str,
) -> list[dict[str, Any]]:
    """Apply provider-specific schema transformations.

    This is a pure function — does not mutate the input schemas.

    Args:
        schemas: List of tool schema dicts (OpenAI function calling format).
        provider: Provider identifier (e.g., "gemini", "xai", "mistral", "openai", "anthropic").

    Returns:
        Transformed list of schemas. Returns a deep copy if any changes were made.
    """
    provider = provider.lower().strip()

    # No adaptation needed for standard providers
    if provider in ("openai", "anthropic", "openrouter"):
        return schemas

    # Deep copy to avoid mutating originals
    adapted = copy.deepcopy(schemas)
    modified = False

    if provider in ("gemini", "google"):
        adapted, changed = _adapt_gemini(adapted)
        modified = modified or changed
    elif provider in ("xai", "grok"):
        adapted, changed = _adapt_xai(adapted)
        modified = modified or changed
    elif provider == "mistral":
        adapted, changed = _adapt_mistral(adapted)
        modified = modified or changed

    # General cleanup for all non-standard providers
    adapted, changed = _general_cleanup(adapted)
    modified = modified or changed

    if modified:
        logger.debug("Adapted %d schemas for provider '%s'", len(adapted), provider)

    return adapted


def _adapt_gemini(schemas: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Gemini rejects additionalProperties, default, $schema, format in nested schemas."""
    changed = False
    for schema in schemas:
        params = schema.get("function", {}).get("parameters", {})
        if _strip_keys_recursive(params, {"additionalProperties", "default", "$schema", "format"}):
            changed = True
    return schemas, changed


def _adapt_xai(schemas: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """xAI/Grok has native web_search that conflicts with our tool."""
    changed = False
    filtered = []
    for schema in schemas:
        name = schema.get("function", {}).get("name", "")
        if name == "web_search":
            logger.info("Filtered out web_search tool for xAI provider (native conflict)")
            changed = True
            continue
        filtered.append(schema)
    return filtered, changed


def _adapt_mistral(schemas: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Mistral doesn't support anyOf/oneOf/allOf — flatten to simple types."""
    changed = False
    for schema in schemas:
        params = schema.get("function", {}).get("parameters", {})
        if _flatten_union_types(params):
            changed = True
    return schemas, changed


def _general_cleanup(schemas: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Ensure schemas follow basic requirements for all providers."""
    changed = False
    for schema in schemas:
        func = schema.get("function", {})
        params = func.get("parameters", {})

        # Ensure top-level has type: "object"
        if params and "type" not in params:
            params["type"] = "object"
            changed = True

        # Ensure properties exists
        if params and "properties" not in params:
            params["properties"] = {}
            changed = True

    return schemas, changed


def _strip_keys_recursive(obj: Any, keys_to_strip: set[str]) -> bool:
    """Recursively remove specified keys from a dict structure.

    Returns True if any keys were actually removed.
    """
    if not isinstance(obj, dict):
        return False

    changed = False
    for key in list(obj.keys()):
        if key in keys_to_strip:
            del obj[key]
            changed = True
        elif isinstance(obj[key], dict):
            if _strip_keys_recursive(obj[key], keys_to_strip):
                changed = True
        elif isinstance(obj[key], list):
            for item in obj[key]:
                if _strip_keys_recursive(item, keys_to_strip):
                    changed = True

    return changed


def _flatten_union_types(obj: Any) -> bool:
    """Replace anyOf/oneOf/allOf with the first variant (lossy but compatible).

    Returns True if any changes were made.
    """
    if not isinstance(obj, dict):
        return False

    changed = False
    for key in list(obj.keys()):
        if key in ("anyOf", "oneOf"):
            variants = obj[key]
            if isinstance(variants, list) and variants:
                # Replace with the first variant
                first = variants[0]
                del obj[key]
                if isinstance(first, dict):
                    obj.update(first)
                changed = True
        elif key == "allOf":
            variants = obj[key]
            if isinstance(variants, list):
                # Merge all variants
                del obj[key]
                for variant in variants:
                    if isinstance(variant, dict):
                        obj.update(variant)
                changed = True
        elif isinstance(obj[key], dict):
            if _flatten_union_types(obj[key]):
                changed = True
        elif isinstance(obj[key], list):
            for item in obj[key]:
                if _flatten_union_types(item):
                    changed = True

    return changed
