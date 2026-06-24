"""Editable prompt loader.

Prompts live as plain text/markdown files in the top-level ``prompts/`` directory
so they can be edited without touching Python. Placeholders use ``<<name>>``
syntax (not ``{}``) so literal JSON braces in a prompt need no escaping.

Edit a file under prompts/, rerun — no code change needed. Files are re-read on
every call (no caching) so edits take effect immediately.
"""

from __future__ import annotations

from pathlib import Path

from . import config

PROMPTS_DIR = config.ROOT / "prompts"


def load_prompt(name: str, **subs: str) -> str:
    """Load prompts/<name>.md and substitute <<key>> placeholders."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt file missing: {path}. Restore it or run from the repo root."
        )
    text = path.read_text(encoding="utf-8")
    for key, value in subs.items():
        text = text.replace(f"<<{key}>>", str(value))
    return text.strip()
