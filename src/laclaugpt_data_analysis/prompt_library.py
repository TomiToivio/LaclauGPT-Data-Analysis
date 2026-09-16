"""Versioned, hashable prompt resources for reproducible analysis.

Prompts are scientific-method resources: inspectable text files loaded without network
access.  The library deliberately keeps rendering small and deterministic.
"""
from __future__ import annotations

import hashlib
import string
from dataclasses import dataclass
from importlib import resources
from importlib.abc import Traversable
from typing import Any


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
        return RenderedPrompt(
            text=text,
            sha256=_sha256(text),
            variables=self.required_variables,
        )

    def provenance(self) -> dict[str, str]:
        return {
            "prompt_id": self.id,
            "prompt_version": self.version,
            "prompt_sha256": self.sha256,
            "prompt_path": self.path,
        }


class PromptLibrary:
    """Load immutable prompt files from a package/resource root.

    The default root is bundled with ``laclaugpt_data_analysis``. External plugins can
    construct a library with their own ``Traversable`` package resource and use the same
    contract without modifying core code.
    """

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
            id=prompt_id,
            version=version,
            text=text,
            sha256=_sha256(text),
            path=relative,
        )


def load_prompt(prompt_id: str, *, version: str = "v1") -> PromptResource:
    """Convenience loader for first-party packaged prompts."""
    return PromptLibrary().load(prompt_id, version=version)


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
