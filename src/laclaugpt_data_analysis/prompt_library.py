"""Versioned, hashable prompt resources for reproducible analysis.

Prompts are scientific-method resources: inspectable text files loaded without network
access. The library deliberately keeps rendering small and deterministic.
"""
from __future__ import annotations

import hashlib
import string
from dataclasses import dataclass
from importlib import resources
from importlib.abc import Traversable
from typing import Any, Literal


class PromptNotFoundError(LookupError):
    """Raised when a requested prompt resource/version does not exist."""


class PromptRenderError(ValueError):
    """Raised when required template variables are missing."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    text: str
    sha256: str
    variables: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PromptMessage:
    """One assembled chat message with explicit provenance."""

    role: Literal["system", "user"]
    text: str
    sha256: str
    prompt_id: str
    prompt_version: str
    prompt_path: str


@dataclass(frozen=True, slots=True)
class PromptStack:
    """Explicit Constitution -> Context -> Task prompt stack."""

    system: PromptMessage
    context: PromptMessage
    task: PromptMessage

    def as_messages(self) -> list[dict[str, str]]:
        return [
            {"role": self.system.role, "content": self.system.text},
            {"role": self.context.role, "content": self.context.text},
            {"role": self.task.role, "content": self.task.text},
        ]

    def provenance(self) -> dict[str, Any]:
        return {
            "architecture": "constitution-context-task",
            "messages": [
                {
                    "role": item.role,
                    "prompt_id": item.prompt_id,
                    "prompt_version": item.prompt_version,
                    "prompt_path": item.prompt_path,
                    "rendered_prompt_sha256": item.sha256,
                }
                for item in (self.system, self.context, self.task)
            ],
        }


@dataclass(frozen=True, slots=True)
class PromptResource:
    id: str
    version: str
    text: str
    sha256: str
    path: str

    @property
    def ref(self) -> str:
        return f"{self.id}:{self.version}"

    @property
    def required_variables(self) -> tuple[str, ...]:
        names: list[str] = []
        for _, field_name, _, _ in string.Formatter().parse(self.text):
            if field_name and field_name not in names:
                names.append(field_name)
        return tuple(names)

    def render(self, **values: Any) -> RenderedPrompt:
        missing = [name for name in self.required_variables if name not in values]
        if missing:
            raise PromptRenderError(
                f"prompt {self.ref} requires variables: {', '.join(missing)}"
            )
        text = self.text.format(**{name: values[name] for name in self.required_variables})
        return RenderedPrompt(text=text, sha256=_sha256(text), variables=self.required_variables)

    def provenance(self) -> dict[str, str]:
        return {
            "prompt_id": self.id,
            "prompt_version": self.version,
            # Backward-compatible alias retained for persisted Phase 1
            # provenance consumers and reproducibility tests.
            "version": self.version,
            "prompt_sha256": self.sha256,
            "prompt_path": self.path,
        }


class PromptLibrary:
    def __init__(self, root: Traversable | None = None) -> None:
        self.root = root or resources.files("laclaugpt_data_analysis").joinpath("prompts")

    @staticmethod
    def _relative_path(prompt_id: str, version: str) -> str:
        if not prompt_id or any(part in {"", ".", ".."} for part in prompt_id.split(".")):
            raise ValueError(f"invalid prompt id: {prompt_id!r}")
        if not version or "/" in version or "\\" in version or version in {".", ".."}:
            raise ValueError(f"invalid prompt version: {version!r}")
        parts = prompt_id.split(".")
        return "/".join((*parts[:-1], f"{parts[-1]}_{version}.md"))

    def load(self, prompt_id: str, *, version: str = "v1") -> PromptResource:
        relative = self._relative_path(prompt_id, version)
        target = self.root.joinpath(*relative.split("/"))
        if not target.is_file():
            raise PromptNotFoundError(f"prompt resource not found: {prompt_id}:{version}")
        text = target.read_text(encoding="utf-8").rstrip() + "\n"
        return PromptResource(
            id=prompt_id, version=version, text=text, sha256=_sha256(text), path=relative
        )


def load_prompt(prompt_id: str, *, version: str = "v1") -> PromptResource:
    return PromptLibrary().load(prompt_id, version=version)


def _render_message(
    resource: PromptResource,
    *,
    role: Literal["system", "user"],
    values: dict[str, Any] | None = None,
) -> PromptMessage:
    values = values or {}
    if resource.required_variables:
        rendered = resource.render(**values)
        text = rendered.text
        rendered_sha = rendered.sha256
    else:
        if values:
            unknown = ", ".join(sorted(values))
            raise PromptRenderError(
                f"prompt {resource.ref} has no variables but values were supplied: {unknown}"
            )
        text = resource.text
        rendered_sha = resource.sha256
    return PromptMessage(
        role=role,
        text=text,
        sha256=rendered_sha,
        prompt_id=resource.id,
        prompt_version=resource.version,
        prompt_path=resource.path,
    )


def assemble_prompt_stack(
    *,
    system_prompt: PromptResource,
    context_prompt: PromptResource,
    task_prompt: PromptResource,
    system_values: dict[str, Any] | None = None,
    context_values: dict[str, Any] | None = None,
    task_values: dict[str, Any] | None = None,
) -> PromptStack:
    """Assemble Constitution -> Research Context -> Current Task messages."""
    return PromptStack(
        system=_render_message(system_prompt, role="system", values=system_values),
        context=_render_message(context_prompt, role="user", values=context_values),
        task=_render_message(task_prompt, role="user", values=task_values),
    )


def prompt_provenance(
    *resources_: PromptResource,
    rendered: RenderedPrompt | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "prompt_resources": [resource.provenance() for resource in resources_]
    }
    if rendered is not None:
        payload["rendered_prompt_sha256"] = rendered.sha256
        payload["rendered_prompt_variables"] = list(rendered.variables)
    return payload
