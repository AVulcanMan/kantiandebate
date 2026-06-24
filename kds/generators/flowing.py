"""Step 7b (CORE) — Flowing drill.

The extracted ArgumentUnit[] from segmentation IS the answer key. The student
flows the clip; we compare their flow to the canonical one (semantic equivalence,
not wording) and report caught / missed / mislabeled.
"""

from __future__ import annotations

from .base import Generator
from ..prompts import load_prompt
from ..schemas import ArgumentUnit, FlowingResult


class FlowingDrill(Generator):
    name = "flowing"

    def grade(
        self, canonical: list[ArgumentUnit], user_flow: str, *, dry_run: bool = False
    ) -> FlowingResult:
        key = "\n".join(
            f"{a.order}. {a.claim}" + (f" (impact: {a.impact})" if a.impact else "")
            for a in canonical
        )
        user = (
            "CANONICAL FLOW (answer key):\n" + key
            + "\n\nSTUDENT FLOW:\n" + user_flow
            + "\n\nGrade as STRICT JSON."
        )
        data = self._generate_json(
            load_prompt("flowing"), user, type_tag="flowing", dry_run=dry_run
        )
        return self._validate(FlowingResult, data)
