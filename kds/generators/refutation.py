"""Step 7 (CORE) — Refutation drill generator.

Two modes over a single ArgumentUnit:
  * drill : present the real argument and prompt the user to refute it.
  * grade : score the user's refutation on direct clash and give an exemplar.
"""

from __future__ import annotations

from .base import Generator
from ..prompts import load_prompt
from ..schemas import ArgumentUnit, RefutationGrade, RefutationPrompt


class RefutationDrill(Generator):
    name = "refutation"

    def _argument_block(self, arg: ArgumentUnit) -> str:
        parts = [f"CLAIM: {arg.claim}"]
        if arg.warrant:
            parts.append(f"WARRANT: {arg.warrant}")
        if arg.impact:
            parts.append(f"IMPACT: {arg.impact}")
        if arg.speaker:
            parts.append(f"SPEAKER: {arg.speaker}")
        return "\n".join(parts)

    def drill(self, arg: ArgumentUnit, *, dry_run: bool = False) -> RefutationPrompt:
        user = "Present this argument for a refutation drill:\n\n" + self._argument_block(arg)
        data = self._generate_json(
            load_prompt("refutation_drill"), user, type_tag="drill", dry_run=dry_run
        )
        return self._validate(RefutationPrompt, data)

    def grade(
        self, arg: ArgumentUnit, user_refutation: str, *, dry_run: bool = False
    ) -> RefutationGrade:
        user = (
            "ARGUMENT:\n" + self._argument_block(arg)
            + "\n\nSTUDENT REFUTATION:\n" + user_refutation
            + "\n\nGrade it as STRICT JSON."
        )
        data = self._generate_json(
            load_prompt("refutation_grade"), user, type_tag="grade", dry_run=dry_run
        )
        return self._validate(RefutationGrade, data)
