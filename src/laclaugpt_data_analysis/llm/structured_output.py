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

from laclaugpt_data_analysis.llm.base import (
    ChatRequest,
    LLMProvider,
    LLMResponse,
    LLMTruncationError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

STRUCTURED_NUM_PREDICT = 4096
STRUCTURED_NUM_CTX = 16384
MAX_STRUCTURED_NUM_PREDICT = 8192

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


def _resolve_schema(node: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    """Resolve local Pydantic JSON-schema references and nullable wrappers."""
    seen: set[str] = set()
    current = node
    while "$ref" in current:
        ref = str(current["$ref"])
        if ref in seen:
            return current
        seen.add(ref)
        target = defs.get(ref.rsplit("/", 1)[-1])
        if not isinstance(target, dict):
            return current
        current = target
    branches = current.get("anyOf")
    if isinstance(branches, list):
        non_null = [branch for branch in branches if isinstance(branch, dict) and branch.get("type") != "null"]
        if len(non_null) == 1:
            return _resolve_schema(non_null[0], defs)
    return current


def _coerce_single_string_lists(
    value: Any,
    schema: dict[str, Any],
    defs: dict[str, Any],
) -> Any:
    """Coerce only unambiguous scalar strings into schema-declared ``list[str]`` values.

    LLMs routinely emit a bare string when a list contains one textual value. This
    normalises that shape before Pydantic validation while leaving dictionaries,
    numbers, and other genuinely incompatible values untouched so real schema errors
    still surface and trigger the normal validation-aware retry.
    """
    node = _resolve_schema(schema, defs)
    node_type = node.get("type")

    if node_type == "array":
        item_schema = node.get("items") or {}
        resolved_item = _resolve_schema(item_schema, defs) if isinstance(item_schema, dict) else {}
        if isinstance(value, str) and resolved_item.get("type") == "string":
            text = value.strip()
            return [text] if text else []
        if isinstance(value, list):
            return [
                _coerce_single_string_lists(item, item_schema, defs)
                if isinstance(item_schema, dict)
                else item
                for item in value
            ]
        return value

    if (node_type == "object" or "properties" in node) and isinstance(value, dict):
        properties = node.get("properties") or {}
        return {
            key: _coerce_single_string_lists(item, properties[key], defs)
            if key in properties and isinstance(properties[key], dict)
            else item
            for key, item in value.items()
        }

    return value


def _validation_feedback(exc: Exception, max_chars: int = 1800) -> str:
    """Compact retry feedback carrying Pydantic/theory validator messages."""
    text = " ".join(str(exc).split())
    return text[:max_chars] if text else type(exc).__name__


def _attach_failure_diagnostics(exc: Exception, response: LLMResponse) -> Exception:
    """Attach provider evidence without changing the public exception type."""
    setattr(exc, "response_raw", response.content)
    setattr(exc, "finish_reason", response.finish_reason)
    return exc


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
    """Validate fenced-or-plain JSON content against the Pydantic model.

    A scalar string is accepted for a schema-declared ``list[str]`` and preserved as
    a one-element list. Other shape errors remain strict.
    """
    payload = json.loads(strip_code_fences(content))
    schema = model_cls.model_json_schema()
    normalized = _coerce_single_string_lists(payload, schema, schema.get("$defs", {}))
    return model_cls.model_validate(normalized)


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
    """Structured output with one retry for truncation or validation failure.

    Structured calls default to a 4096-token output budget inside a 16K context.
    If the provider explicitly reports a length stop, the retry doubles only the
    output budget (up to 8192) and does not add schema-correction feedback.
    """
    shape_prompt = build_structured_prompt(user_prompt, model_cls)
    run_options = dict(options or {})
    run_options.setdefault("num_predict", STRUCTURED_NUM_PREDICT)
    run_options["num_ctx"] = max(int(run_options.get("num_ctx", 0) or 0), STRUCTURED_NUM_CTX)

    for attempt in (1, 2):
        request = ChatRequest(
            model=model,
            system=system_prompt,
            user=shape_prompt,
            options=dict(run_options),
            schema=schema,
            allow_cloud_fallback=allow_cloud_fallback,
        )
        response = provider.chat(request)

        if response.truncated:
            logger.warning(
                "structured generation truncated (attempt %d, finish_reason=%s, num_predict=%s)",
                attempt,
                response.finish_reason or "unknown",
                run_options.get("num_predict"),
            )
            if attempt == 2:
                exc = LLMTruncationError(
                    "structured generation exhausted the output budget "
                    f"(finish_reason={response.finish_reason or 'unknown'}, "
                    f"num_predict={run_options.get('num_predict')})"
                )
                raise _attach_failure_diagnostics(exc, response)
            current_budget = int(run_options.get("num_predict", STRUCTURED_NUM_PREDICT))
            next_budget = min(
                max(current_budget * 2, STRUCTURED_NUM_PREDICT),
                MAX_STRUCTURED_NUM_PREDICT,
            )
            run_options["num_predict"] = next_budget
            run_options["num_ctx"] = max(
                int(run_options.get("num_ctx", 0) or 0),
                STRUCTURED_NUM_CTX,
                next_budget * 2,
            )
            continue

        try:
            parsed = parse_structured(response.content, model_cls)
            return parsed, response
        except Exception as exc:
            logger.warning("structured parse failed (attempt %d): %s", attempt, exc)
            if attempt == 2:
                raise _attach_failure_diagnostics(exc, response)
            shape_prompt += (
                "\n\n### Validation failure from your previous answer\n"
                f"{_validation_feedback(exc)}\n"
                "Correct the specific schema/theory rule above. Return ONLY the JSON "
                "object with exactly the required fields; do not explain the correction."
            )
    raise RuntimeError("unreachable")  # pragma: no cover
