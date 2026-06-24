"""Step 9 — one-command pipeline: YouTube URL -> ready-to-run drills.

Chains: youtube ingest -> transcribe -> segment -> persist flow, and surfaces the
human-review queue. Each stage caches, so re-runs are cheap.
"""

from __future__ import annotations

from typing import Optional

from .. import config, store
from ..schemas import ArgumentUnit, Transcript
from .segment import Segmenter, review_queue
from .transcribe import transcribe
from .youtube import fetch_audio


def run_pipeline(url: str, *, settings: Optional[config.Settings] = None) -> dict:
    settings = settings or config.get_settings()

    meta = fetch_audio(url)
    vid = meta["video_id"]

    # Cache transcript on disk.
    tpath = config.TRANSCRIPTS_DIR / f"{vid}.json"
    if tpath.exists():
        from .transcript_io import load_transcript

        transcript: Transcript = load_transcript(tpath)
    else:
        transcript = transcribe(
            meta["audio_path"],
            source_url=url,
            title=meta.get("title"),
            video_id=vid,
            settings=settings,
        )

    # Cache flow in the store.
    arguments: list[ArgumentUnit] = store.load_arguments(vid)
    if not arguments:
        arguments = Segmenter().segment(transcript, verbose=True)
        store.save_arguments(vid, arguments)

    queue = review_queue(arguments)
    return {
        "video_id": vid,
        "title": meta.get("title"),
        "n_segments": len(transcript.segments),
        "n_arguments": len(arguments),
        "n_needs_review": len(queue),
        "arguments": arguments,
        "review_queue": queue,
    }
