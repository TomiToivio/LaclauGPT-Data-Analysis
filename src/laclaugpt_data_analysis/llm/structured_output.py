"""Structured-output handling with one validation-aware retry.

Migrated from the monolith's ``llm.py``: schema-shaped JSON extraction, a
compact example rendered from the Pydantic schema, and a retry that feeds the
actual validation error back to the model (length-capped so malformed output
cannot inflate the next prompt without bound).
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, TypeVar

from pydantic import BaseModel

from laclaugpt_data_analysis.llm.base import (
    ChatRequest,
    LLMProvider,
    LLMResponse,
    LLMTruncationError,
)
from laclaugpt_data_analysis.llm.json_repair import join_repairs, repaired_candidate

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

STRUCTURED_NUM_PREDICT = 4096
STRUCTURED_NUM_CTX = 16384
MAX_STRUCTURED_NUM_PREDICT = 16384

STRUCTURED_NUM_PREDICT_ENV = "LACLAUGPT_STRUCTURED_NUM_PREDICT"
STRUCTURED_NUM_CTX_ENV = "LACLAUGPT_STRUCTURED_NUM_CTX"
MAX_STRUCTURED_NUM_PREDICT_ENV = "LACLAUGPT_MAX_STRUCTURED_NUM_PREDICT"


def _positive_int_env(name: str, default: int) -> int:
    """Read a positive integer runtime override without making imports fragile."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("ignoring invalid %s=%r; using %d", name, raw, default)
        return default
    if value <= 0:
        logger.warning("ignoring non-positive %s=%r; using %d", name, raw, default)
        return default
    return value


def structured_output_ceiling() -> int:
    """Return the active structured-output ceiling after runtime overrides."""
    return _positive_int_env(
        MAX_STRUCTURED_NUM_PREDICT_ENV, MAX_STRUCTURED_NUM_PREDICT
    )

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


_JSON_KEY_HINT = re.compile(r"\s*:")

_PROSE_PREFIX_RE = re.compile(r"[^\s]*?")


def _string_literal_spans(text: str) -> list[tuple[int, int]]:
    """Spans of double-quoted string literals, tolerant of escapes."""
    spans: list[tuple[int, int]] = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == '"':
            start = index
            index += 1
            while index < length:
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == '"':
                    break
                index += 1
            spans.append((start, min(index + 1, length)))
        index += 1
    return spans


def sanitize_structured_excerpt(content: str, limit: int = 400) -> str:
    """A structural excerpt with every string *value* elided and every key kept.

    Keys are schema field names and carry the diagnosis; values are research text and
    must not be copied into logs or issues. Truncation is marked explicitly.
    """
    head = content[:limit]
    spans = _string_literal_spans(head)
    pieces: list[str] = []
    cursor = 0
    for start, stop in spans:
        pieces.append(head[cursor:start])
        literal = head[start:stop]
        after = head[stop:stop + 8]
        is_key = bool(_JSON_KEY_HINT.match(after))
        if is_key and len(literal) <= 64:
            pieces.append(literal)
        else:
            pieces.append('"<elided>"')
        cursor = stop
    pieces.append(head[cursor:])
    excerpt = "".join(pieces)
    if len(content) > limit:
        excerpt += f"... <{len(content) - limit} more chars>"
    return excerpt


def classify_json_failure(content: str, exc: Exception) -> dict[str, object]:
    """Name why a structured response could not be parsed, from the response itself.

    The pipeline logged only ``JSONDecodeError``, which is not enough to choose a fix:
    a prose wrapper needs stripping, a length stop needs a bigger budget, and a
    trailing comma needs a repair. This returns the mode, the character position the
    parser complained about, and structural counts, so the next diagnosis is decidable
    without keeping the payload.
    """
    text = content or ""
    stripped = strip_code_fences(text)
    position = getattr(exc, "pos", None)
    mode = "json_decode_error"
    detail = ""

    if not text.strip():
        mode = "empty_response"
    elif not stripped.strip():
        mode = "fences_only"
    else:
        first_open = min(
            (index for index in (stripped.find("{"), stripped.find("[")) if index != -1),
            default=-1,
        )
        if first_open > 0 and stripped[:first_open].strip():
            mode = "prose_wrapped"
            detail = stripped[:first_open].strip()[:60]
        elif stripped[-1:] not in ("}", "]"):
            last_close = max(stripped.rfind("}"), stripped.rfind("]"))
            if last_close != -1 and stripped[last_close + 1:].strip():
                mode = "trailing_text"
                detail = stripped[last_close + 1:].strip()[:60]
            elif stripped.count("{") != stripped.count("}") or stripped.count("[") != stripped.count("]"):
                mode = "unbalanced_structure"
            else:
                mode = "trailing_text"
        elif re.search(r",\s*[}\]]", stripped):
            mode = "trailing_comma"
        elif re.search(r"'[^']*'\s*:", stripped):
            mode = "single_quoted_key"
        elif re.search(r"[{,]\s*[A-Za-z_][A-Za-z0-9_]*\s*:", stripped):
            mode = "unquoted_key"
        elif "\\x" in stripped or re.search(r"\\[^\"\\\\/bfnrtu]", stripped):
            mode = "invalid_escape"

    return {
        "mode": mode,
        "position": position,
        "chars": len(text),
        "brace_balance": stripped.count("{") - stripped.count("}"),
        "bracket_balance": stripped.count("[") - stripped.count("]"),
        "detail": detail,
        "excerpt": sanitize_structured_excerpt(stripped),
    }


def _validation_feedback(exc: Exception, max_chars: int = 1800) -> str:
    """Compact retry feedback carrying Pydantic/theory validator messages."""
    text = " ".join(str(exc).split())
    return text[:max_chars] if text else type(exc).__name__


def classify_json_decode_failure(content: str, exc: json.JSONDecodeError) -> dict[str, Any]:
    """Describe malformed output without logging source text or model responses.

    These are heuristic shape labels, not an automatic JSON repair policy.
    The existing private durable failure capture retains bounded raw evidence.
    """
    text = content.strip()
    stripped = strip_code_fences(text)
    prefix = stripped[: min(exc.pos, len(stripped))]
    suffix = stripped[min(exc.pos, len(stripped)):]
    if text.startswith("```") or text.endswith("```"):
        shape = "fenced"
    elif stripped.startswith(("Here is", "Sure,", "JSON:", "json:")):
        shape = "prose_wrapper"
    elif re.search(r",\s*[}\]]", stripped):
        shape = "trailing_comma"
    elif stripped.startswith(("{", "[")) and ("'" in stripped[:100]) and ('"' not in stripped[:100]):
        shape = "single_quotes_possible"
    elif stripped.startswith(("{", "[")) and (not suffix or exc.pos >= len(stripped) - 2):
        shape = "possibly_truncated"
    else:
        shape = "other_invalid_json"
    return {
        "decode_shape": shape,
        "decode_position": exc.pos,
        "decode_line": exc.lineno,
        "decode_column": exc.colno,
        "decode_response_chars": len(content),
        "decode_prefix_chars": len(prefix),
    }


def _attach_failure_diagnostics(exc: Exception, response: LLMResponse) -> None:
    """Attach provider evidence without changing the public exception type."""
    exc.response_raw = response.content
    exc.finish_reason = response.finish_reason
    if isinstance(exc, json.JSONDecodeError):
        exc.decode_diagnostics = classify_json_decode_failure(response.content, exc)


def _attach_json_failure_diagnostics(exc: Exception, response: LLMResponse) -> None:
    """Attach a classified, value-elided diagnosis of an unparseable response (#343).

    ``response_raw`` keeps the payload itself for an operator who needs it; these
    fields are what belongs in a log line or an issue, because every string *value*
    is elided and only schema keys survive.
    """
    diagnosis = classify_json_failure(response.content, exc)
    exc.json_failure = diagnosis
    logger.warning(
        "structured JSON decode failed: mode=%s pos=%s chars=%s brace_balance=%s excerpt=%s",
        diagnosis["mode"],
        diagnosis["position"],
        diagnosis["chars"],
        diagnosis["brace_balance"],
        diagnosis["excerpt"],
    )


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

    A malformed response gets one bounded *structural* repair before it is treated as
    a validation failure (#343). Measured against the worker's own captured failures,
    that recovers half the ``JSONDecodeError`` class. The repair never rewrites string
    contents and never invents content, so it can only turn a discard into a
    validation attempt - the model remains the contract - and it is logged. Set
    ``LACLAUGPT_JSON_REPAIR=0`` to disable it, which restores the pre-#343 behaviour.
    """
    text = strip_code_fences(content)
    text, repairs = repaired_candidate(text)
    if repairs:
        logger.warning(
            "repaired malformed JSON before validation (%s; %d chars)",
            join_repairs(repairs),
            len(content),
        )
    payload = json.loads(text)
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
    """Structured output with bounded validation retry and truncation escalation.

    The default output ladder is 4096 -> 8192 -> 16384 tokens. A length stop
    widens only the output budget and grows num_ctx to at least twice that
    budget. The ladder is bounded within one call, so an exhausted document is
    still terminalized by the worker instead of poisoning later hourly cycles.

    Runtime overrides:
    LACLAUGPT_STRUCTURED_NUM_PREDICT,
    LACLAUGPT_STRUCTURED_NUM_CTX, and
    LACLAUGPT_MAX_STRUCTURED_NUM_PREDICT.
    Explicit request options still win for the initial per-call budget/context.
    """
    shape_prompt = build_structured_prompt(user_prompt, model_cls)
    run_options = dict(options or {})

    default_budget = _positive_int_env(
        STRUCTURED_NUM_PREDICT_ENV, STRUCTURED_NUM_PREDICT
    )
    minimum_ctx = _positive_int_env(STRUCTURED_NUM_CTX_ENV, STRUCTURED_NUM_CTX)
    configured_ceiling = structured_output_ceiling()

    run_options.setdefault("num_predict", default_budget)
    current_budget = int(run_options["num_predict"])
    ceiling = max(current_budget, configured_ceiling)
    run_options["num_ctx"] = max(
        int(run_options.get("num_ctx", 0) or 0),
        minimum_ctx,
    )

    validation_failures = 0
    call_attempt = 0

    while True:
        call_attempt += 1
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
                "structured generation truncated (call %d, finish_reason=%s, num_predict=%s)",
                call_attempt,
                response.finish_reason or "unknown",
                run_options.get("num_predict"),
            )
            current_budget = int(run_options.get("num_predict", default_budget))
            if current_budget >= ceiling:
                exc = LLMTruncationError(
                    "structured generation exhausted the output budget "
                    f"(finish_reason={response.finish_reason or 'unknown'}, "
                    f"num_predict={current_budget}, ceiling={ceiling})"
                )
                _attach_failure_diagnostics(exc, response)
                # A length stop proves only a lower bound, not the exact number
                # of tokens needed to finish the schema. Do not invent a count.
                exc.output_budget_tokens = current_budget
                exc.required_output_tokens_lower_bound = current_budget + 1
                exc.generated_output_chars = len(response.content)
                raise exc from None

            next_budget = min(
                max(current_budget * 2, default_budget),
                ceiling,
            )
            run_options["num_predict"] = next_budget
            run_options["num_ctx"] = max(
                int(run_options.get("num_ctx", 0) or 0),
                minimum_ctx,
                next_budget * 2,
            )
            continue

        try:
            parsed = parse_structured(response.content, model_cls)
            return parsed, response
        except Exception as exc:
            validation_failures += 1
            logger.warning(
                "structured parse failed (validation attempt %d): %s",
                validation_failures,
                exc,
            )
            if isinstance(exc, json.JSONDecodeError):
                # A decode failure is not a validation failure: naming the shape is the
                # only way to choose between stripping, repairing and budgeting (#343).
                _attach_json_failure_diagnostics(exc, response)
            if validation_failures >= 2:
                _attach_failure_diagnostics(exc, response)
                raise
            shape_prompt += (
                "\n\n### Validation failure from your previous answer\n"
                f"{_validation_feedback(exc)}\n"
                "Correct the specific schema/theory rule above. Return ONLY the JSON "
                "object with exactly the required fields; do not explain the correction."
            )
