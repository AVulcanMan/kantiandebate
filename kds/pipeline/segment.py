"""Step 6 — Argument segmentation: Segment[] -> ArgumentUnit[].

The hardest LLM task in the pipeline and the quality cap for every drill: a bad
claim/warrant split yields a nonsense refutation target. Low-confidence units are
flagged for the human-review queue (see needs_review on ArgumentUnit).

This produces the canonical "flow" of the round that refutation / flowing /
round-vision drills all consume.
"""

from __future__ import annotations

import time
from typing import Iterator, Optional

from ..generators.base import Generator
from ..prompts import load_prompt
from ..schemas import ArgumentList, ArgumentUnit, Segment, Transcript

# Free-tier TPM is small (~12k on Groq), so each window's input must stay well
# under it with room for the output reservation. ~16k chars ≈ 4k input tokens.
_WINDOW_CHARS = 16000
_PACE_SECONDS = 30  # spacing between windows to respect tokens-per-minute

class Segmenter(Generator):
    name = "segmentation"

    def segment(
        self,
        transcript: Transcript,
        *,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> list[ArgumentUnit]:
        """Segment a (possibly long) round by chunking into token-budgeted windows.

        Per-window segmentation respects free-tier rate limits and tends to be
        more accurate than one giant call. Orders are made contiguous across
        windows.
        """
        title = transcript.metadata.title if transcript.metadata else None
        windows = list(_window_segments(transcript.segments, _WINDOW_CHARS))
        all_args: list[ArgumentUnit] = []
        for i, window in enumerate(windows):
            user = self._render(window, title, window_idx=i, n_windows=len(windows))
            data = self._generate_json(
                load_prompt("segmentation"), user, type_tag="segmentation",
                max_tokens=2048, dry_run=dry_run,
            )
            args = self._validate(ArgumentList, data).arguments
            all_args.extend(args)
            if verbose:
                print(f"  window {i + 1}/{len(windows)}: +{len(args)} arguments")
            # Pace to stay under tokens-per-minute (skip after the last window).
            if not dry_run and i < len(windows) - 1:
                time.sleep(_PACE_SECONDS)

        # Make order contiguous across the whole round.
        for i, arg in enumerate(all_args, start=1):
            arg.order = i
        return all_args

    def _render(
        self,
        segments: list[Segment],
        title: Optional[str],
        *,
        window_idx: int = 0,
        n_windows: int = 1,
    ) -> str:
        lines = []
        if title:
            lines.append(f"ROUND: {title}")
        if n_windows > 1:
            lines.append(f"(Transcript window {window_idx + 1} of {n_windows}.)")
        lines.append("\nTRANSCRIPT:")
        for seg in segments:
            who = f"[{seg.speaker}] " if seg.speaker else ""
            ts = f"({seg.start:.0f}s) " if seg.start is not None else ""
            lines.append(f"{ts}{who}{seg.text}")
        lines.append("\nExtract the flow as STRICT JSON now.")
        return "\n".join(lines)


def _window_segments(segments: list[Segment], max_chars: int) -> Iterator[list[Segment]]:
    """Yield consecutive groups of segments whose combined text <= max_chars."""
    window: list[Segment] = []
    size = 0
    for seg in segments:
        seg_len = len(seg.text) + 1
        if window and size + seg_len > max_chars:
            yield window
            window, size = [], 0
        window.append(seg)
        size += seg_len
    if window:
        yield window


def review_queue(arguments: list[ArgumentUnit]) -> list[ArgumentUnit]:
    """Return the arguments that need human review (low confidence)."""
    return [a for a in arguments if a.needs_review]
