"""Step 7c (CORE) — Round Vision drill.

Pause a real round at a snapshot (after speech N) and quiz holistic awareness:
central clash, biggest dropped argument, who's ahead and why, what the next
speaker must do. Grade against the extracted flow, then REVEAL what actually
happened next (predict-then-reveal).
"""

from __future__ import annotations

from typing import Optional

from .base import Generator
from ..prompts import load_prompt
from ..schemas import ArgumentUnit, RoundVisionResult

QUESTIONS = {
    "central_clash": "What is the central clash of the round so far?",
    "top_drop": "What is the biggest dropped or under-covered argument?",
    "who_is_ahead": "Who is ahead right now and why?",
    "next_speaker_must_do": "What must the next speaker do to win?",
}


class RoundVisionDrill(Generator):
    name = "round_vision"

    @staticmethod
    def split_snapshot(
        arguments: list[ArgumentUnit], after_speech: Optional[int] = None
    ) -> tuple[list[ArgumentUnit], list[ArgumentUnit]]:
        """Split the flow into (before, after) a snapshot point.

        Defaults to roughly two-thirds through the round.
        """
        ordered = sorted(arguments, key=lambda a: a.order or 0)
        cut = after_speech if after_speech is not None else max(1, (len(ordered) * 2) // 3)
        return ordered[:cut], ordered[cut:]

    def build_prompt(self, before: list[ArgumentUnit]) -> str:
        flow = "\n".join(
            f"{a.order}. [{a.speaker or '?'}] {a.claim}"
            + (f" -> {a.impact}" if a.impact else "")
            for a in before
        )
        qs = "\n".join(f"- {k}: {v}" for k, v in QUESTIONS.items())
        return f"ROUND SO FAR:\n{flow}\n\nAnswer these:\n{qs}"

    def grade(
        self,
        before: list[ArgumentUnit],
        after: list[ArgumentUnit],
        user_answers: dict[str, str],
        *,
        dry_run: bool = False,
    ) -> RoundVisionResult:
        flow_before = "\n".join(f"{a.order}. [{a.speaker or '?'}] {a.claim}" for a in before)
        flow_after = "\n".join(f"{a.order}. [{a.speaker or '?'}] {a.claim}" for a in after) or "(round ended)"
        answers = "\n".join(f"- {k}: {v}" for k, v in user_answers.items())
        user = (
            f"FLOW UP TO SNAPSHOT:\n{flow_before}\n\n"
            f"WHAT CAME AFTER (hidden from student):\n{flow_after}\n\n"
            f"STUDENT ANSWERS:\n{answers}\n\nGrade and reveal as STRICT JSON."
        )
        data = self._generate_json(
            load_prompt("round_vision"), user, type_tag="round_vision",
            max_tokens=1536, dry_run=dry_run,
        )
        return self._validate(RoundVisionResult, data)
