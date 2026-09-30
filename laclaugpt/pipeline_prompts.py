"""Project-system-prompt boundary for the human-written pipeline."""

from __future__ import annotations

from pathlib import Path


def load_project_system_prompt(project: str, data_dir: Path = Path("data")) -> str:
    """Load a project prompt from runtime/private data.

    Public code should not embed private source lists, annotations, or operational
    project instructions. A deployment may place prompts at:
        data/projects/<project>/system_prompt.md
    """

    path = data_dir / "projects" / project / "system_prompt.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def combine_prompts(method_prompt: str, project_prompt: str) -> str:
    """Keep reusable method instructions visibly separate from project context."""
    parts = [part.strip() for part in (method_prompt, project_prompt) if part.strip()]
    return "\n\n--- PROJECT CONTEXT ---\n\n".join(parts)
