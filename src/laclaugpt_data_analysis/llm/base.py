"""Provider-neutral LLM contracts."""
from __future__ import annotations

from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class StructuredOutputError(LLMError):
    pass


class LLMResponse(BaseModel):
    content: str
    provider: str
    model: str
    endpoint: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMProvider(Protocol):
    def chat(self, *, system_prompt: str, user_prompt: str, model: str | None = None,
             options: dict[str, Any] | None = None,
             schema: dict[str, Any] | None = None) -> LLMResponse: ...

    def structured(self, model_cls: type[T], *, system_prompt: str,
                   user_prompt: str, model: str | None = None,
                   options: dict[str, Any] | None = None) -> tuple[T, LLMResponse]: ...
