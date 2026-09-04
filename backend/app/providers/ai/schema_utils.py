"""Adapt JSON schemas for OpenAI structured outputs (strict mode)."""

from __future__ import annotations

import copy
from typing import Any


def prepare_openai_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copied schema adjusted for OpenAI strict JSON schema mode.

    OpenAI requires object nodes to set additionalProperties=false and to list
    every property under `required`. Pydantic schemas often omit these.
    """
    adapted = copy.deepcopy(schema)
    _normalize_node(adapted)
    return adapted


def _normalize_node(node: Any) -> None:
    if not isinstance(node, dict):
        return

    # Walk nested schema containers first
    for key in ("definitions", "$defs"):
        defs = node.get(key)
        if isinstance(defs, dict):
            for value in defs.values():
                _normalize_node(value)

    for key in ("anyOf", "oneOf", "allOf"):
        options = node.get(key)
        if isinstance(options, list):
            for option in options:
                _normalize_node(option)

    if "items" in node:
        _normalize_node(node["items"])

    properties = node.get("properties")
    if isinstance(properties, dict):
        for value in properties.values():
            _normalize_node(value)
        # Strict mode: every property must be required
        node["additionalProperties"] = False
        node["required"] = list(properties.keys())

    # Root object without properties still needs the flag when type is object
    if node.get("type") == "object" and "additionalProperties" not in node:
        node["additionalProperties"] = False
