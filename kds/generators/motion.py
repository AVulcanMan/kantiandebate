"""Step 11 + 14 — Type-conditioned motion generator with optional news-RAG.

A single model conditioned by a type tag (policy / value / fact) — no per-type
adapters. Few-shots are drawn class-balanced from the corpus to counter the 5:1
policy skew. When a theme and/or news grounding is supplied, recent headlines are
retrieved (Google News RSS, no key) and injected so motions are timely.
"""

from __future__ import annotations

from typing import Optional

import re

from .base import Generator
from ..corpus.sample import sample_by_class
from ..prompts import PROMPTS_DIR, load_prompt
from ..rag.news import context_block, fetch_headlines
from ..schemas import Motion, MotionList
from ..taxonomy import MotionType, definition


def _type_guidance(motion_type: str) -> str:
    """Read the per-type guidance section from prompts/motion_type_guidance.md."""
    text = (PROMPTS_DIR / "motion_type_guidance.md").read_text(encoding="utf-8")
    # Sections delimited by "## <type>" headers.
    sections = dict(
        re.findall(r"^##\s*(\w+)\s*\n(.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    )
    return sections.get(motion_type, "").strip()


class MotionGenerator(Generator):
    name = "motion"

    def generate(
        self,
        motion_type: str,
        *,
        n: int = 5,
        theme: Optional[str] = None,
        use_news: bool = False,
        dry_run: bool = False,
    ) -> list[Motion]:
        mt = MotionType(motion_type)

        theme_line = f"- Center the motions on this THEME: {theme}." if theme else ""
        system = load_prompt(
            "motion",
            type_definition=definition(mt),
            type_guidance=_type_guidance(mt.value),
            motion_type=mt.value,
            theme_line=theme_line,
        )

        # Class-balanced few-shots: examples of the requested type (count/quality
        # are editable in config.toml [motion]).
        from .. import config

        mcfg = config.motion_config()
        try:
            examples = sample_by_class(
                mt.value,
                n=mcfg["n_fewshots"],
                min_confidence=mcfg["fewshot_min_confidence"],
                seed=None,
            )
        except FileNotFoundError:
            examples = []
        fewshot_block = ""
        if examples:
            fewshot_block = "EXAMPLE " + mt.value.upper() + " MOTIONS:\n" + "\n".join(
                f"- {e}" for e in examples
            )

        news_block = ""
        if use_news or theme:
            articles = fetch_headlines(theme=theme, n=mcfg["news_count"])
            news_block = context_block(articles)

        user_parts = [f"Write {n} fresh {mt.value} motions."]
        if fewshot_block:
            user_parts.append(fewshot_block)
        if news_block:
            user_parts.append(news_block)
        user_parts.append("Return STRICT JSON now.")
        user = "\n\n".join(user_parts)

        data = self._generate_json(
            system, user, type_tag=mt.value, max_tokens=1536, dry_run=dry_run
        )
        motions = self._validate(MotionList, data).motions
        # Enforce the requested type tag regardless of what the model labeled.
        for m in motions:
            m.motion_type = mt
        return motions
