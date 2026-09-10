"""Prompt registry — every LLM prompt lives in its own ``.md`` file.

Prompts are content, not code: keeping them in Markdown makes them reviewable in
diffs by non-engineers and prevents the indentation drift that plagued inline
triple-quoted strings. ``{}`` in a prompt file is a ``str.format`` placeholder,
so literal braces must be doubled.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

PROMPT_DIR = Path(__file__).parent

# Markdown files that document the folder rather than feed a model.
_NON_PROMPT_STEMS = frozenset({"README"})


class PromptNotFoundError(LookupError):
    """Raised when a prompt file is missing — a deployment/packaging bug."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Prompt not found: {name}.md in {PROMPT_DIR}")


@cache
def load_prompt(name: str) -> str:
    """Return the raw prompt text for ``name`` (without the ``.md`` suffix)."""
    path = PROMPT_DIR / f"{name}.md"
    if not path.is_file():
        raise PromptNotFoundError(name)
    return path.read_text(encoding="utf-8").strip()


def render_prompt(name: str, /, **values: object) -> str:
    """Load a prompt and substitute ``{placeholder}`` values."""
    return load_prompt(name).format(**values)


def available_prompts() -> list[str]:
    """Prompt names available on disk, for tests and diagnostics."""
    return sorted(
        path.stem for path in PROMPT_DIR.glob("*.md") if path.stem not in _NON_PROMPT_STEMS
    )


__all__ = [
    "PROMPT_DIR",
    "PromptNotFoundError",
    "available_prompts",
    "load_prompt",
    "render_prompt",
]
