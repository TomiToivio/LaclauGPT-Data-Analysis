"""Lazy Ollama provider adapter."""
from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .base import LLMResponse, StructuredOutputError
from .routing import ModelRoute

T = TypeVar("T", bound=BaseModel)

DEFAULT_OPTIONS = {"temperature": 0.0, "num_ctx": 8192, "num_predict": 2048}


class OllamaProvider:
    def __init__(self, route: ModelRoute, *, host: str = "", timeout_seconds: float = 120.0):
        self.route = route
        self.host = host
        self.timeout_seconds = timeout_seconds

    def _client(self):
        try:
            import ollama
        except ImportError as exc:
            raise RuntimeError("Ollama support requires: pip install '.[ollama]'") from exc
        kwargs: dict[str, Any] = {}
        if self.host:
            kwargs["host"] = self.host
        return ollama.Client(**kwargs)

    def chat(self, *, system_prompt: str, user_prompt: str, model: str | None = None,
             options: dict[str, Any] | None = None,
             schema: dict[str, Any] | None = None) -> LLMResponse:
        use_model = model or self.route.model
        is_cloud = use_model.endswith("-cloud") or use_model.endswith(":cloud")
        if is_cloud and not self.route.allow_cloud:
            raise ValueError("cloud inference is not allowed by this route")
        opts = dict(DEFAULT_OPTIONS)
        if options:
            opts.update(options)
        kwargs: dict[str, Any] = {}
        if schema is not None:
            kwargs["format"] = schema
        response = self._client().chat(
            model=use_model,
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": user_prompt}],
            options=opts,
            **kwargs,
        )
        content = response["message"]["content"]
        return LLMResponse(
            content=content,
            provider="ollama",
            model=use_model,
            endpoint=self.host or "default",
            metadata={"mode": "cloud" if is_cloud else "local", "options": opts},
        )

    def structured(self, model_cls: type[T], *, system_prompt: str,
                   user_prompt: str, model: str | None = None,
                   options: dict[str, Any] | None = None) -> tuple[T, LLMResponse]:
        schema = model_cls.model_json_schema()
        response = self.chat(system_prompt=system_prompt, user_prompt=user_prompt,
                             model=model, options=options, schema=schema)
        text = _strip_fences(response.content)
        try:
            payload = json.loads(text)
            return model_cls.model_validate(payload), response
        except (json.JSONDecodeError, ValidationError) as first:
            retry_prompt = (
                user_prompt
                + "\n\nReturn ONLY valid JSON matching this schema. Previous validation error: "
                + " ".join(str(first).split())[:1200]
            )
            retry = self.chat(system_prompt=system_prompt, user_prompt=retry_prompt,
                              model=model, options=options, schema=schema)
            try:
                payload = json.loads(_strip_fences(retry.content))
                return model_cls.model_validate(payload), retry
            except (json.JSONDecodeError, ValidationError) as second:
                raise StructuredOutputError(str(second)) from second


def _strip_fences(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        first = value.find("\n")
        if first >= 0:
            value = value[first + 1:]
        if value.rstrip().endswith("```"):
            value = value.rstrip()[:-3]
    return value.strip()
