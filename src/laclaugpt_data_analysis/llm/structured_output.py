"""Structured-output handling with one validation-aware retry.

Migrated from the monolith's ``llm.py``: schema-shaped JSON extraction, a
compact example rendered from the Pydantic schema, and a retry that feeds the
actual validation error back to the model (length-capped so malformed output
cannot inflate the next prompt without bound).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel

from laclaugpt_data_analysis.llm.base import ChatRequest, LLMProvider, LLMResponse

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\n?|\n?```$")


def strip_code_fences(content: str) -> str:
    """Strip one surrounding markdown code fence, if present."""
    text = content.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
    if text.rstrip().endswith("```"):
        text = text.rstrip()[:-3]
    return text.strip()


def _schema_example(model_cls: type[T]) -> str:
    schema = model_cls.model_json_schema()
    defs = schema.get("$defs", {})

    def render(node: dict, depth: int) -> str:
        if depth > 12:
            return '"..."'
        if "$ref" in node:
            target = defs.get(str(node["$ref"]).rsplit("/", 1)[-1])
            return render(target, depth + 1) if target else '"..."'
        if "const" in node:
            return json.dumps(node["const"], ensure_ascii=False)
        if "enum" in node and node["enum"]:
            opts = " | ".join(str(opt) for opt in node["enum"])
            return f'"<{opts}>"'
        branches = node.get("anyOf")
        if branches:
            non_null = [branch for branch in branches if branch.get("type") != "null"]
            return render((non_null or branches)[0], depth)
        node_type = node.get("type")
        if node_type == "boolean":
            return "true"
        if node_type in ("number", "integer"):
            return "0"
        if node_type == "array":
            return f'[{render(node.get("items") or {}, depth + 1)}]'
        if node_type == "object" or "properties" in node:
            props = node.get("properties") or {}
            if not props:
                return "{}"
            parts = [
                f'{"  " * (depth + 1)}"{key}": {render(sub, depth + 1)}'
                for key, sub in props.items()
            ]
            return "{\n" + ",\n".join(parts) + "\n" + "  " * depth + "}"
        return '"..."'

    return render(schema, 0)


def _validation_feedback(exc: Exception, max_chars: int = 1800) -> str:
    """Compact retry feedback carrying Pydantic/theory validator messages."""
    text = " ".join(str(exc).split())
    return text[:max_chars] if text else type(exc).__name__


def build_structured_prompt(user_prompt: str, model_cls: type[T]) -> str:
    """Append the required-output-JSON-shape contract to a user prompt."""
    shape = _schema_example(model_cls)
    return user_prompt + (
        "\n\n### **Required output JSON shape**\n"
        "Return ONLY a single JSON object (no markdown fences, no commentary) "
        "with EXACTLY the following field names and nesting:\n"
        f"{shape}\n"
        "Every listed field must be present (use [] for empty lists and \"\" for "
        "empty strings — never null); do not invent extra fields or nest fields differently."
    )


def parse_structured(content: str, model_cls: type[T]) -> T:
    """Validate fenced-or-plain JSON content against the Pydantic model."""
    return model_cls.model_validate_json(strip_code_fences(content))


def chat_structured(
    provider: LLMProvider,
    model_cls: type[T],
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    options: dict[str, Any] | None = None,
    schema: dict[str, Any] | None = None,
    allow_cloud_fallback: bool | None = None,
) -> tuple[T, LLMResponse]:
    """Structured output with one validation-aware retry."""
    shape_prompt = build_structured_prompt(user_prompt, model_cls)
    for attempt in (1, 2):
        request = ChatRequest(
            model=model,
            system=system_prompt,
            user=shape_prompt,
            options=options or {},
            schema=schema,
            allow_cloud_fallback=allow_cloud_fallback,
        )
        response = provider.chat(request)
        try:
            parsed = parse_structured(response.content, model_cls)
            return parsed, response
        except Exception as exc:
            logger.warning("structured parse failed (attempt %d): %s", attempt, exc)
            if attempt == 2:
                raise
            shape_prompt += (
                "\n\n### Validation failure from your previous answer\n"
                f"{_validation_feedback(exc)}\n"
                "Correct the specific schema/theory rule above. Return ONLY the JSON "
                "object with exactly the required fields; do not explain the correction."
            )
    raise RuntimeError("unreachable")  # pragma: no cover
