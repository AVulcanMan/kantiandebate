"""Footage pipeline: YouTube -> audio -> transcript -> argument units.

Phase 0 ships only the transcript I/O contract (transcript_io). youtube,
transcribe, and segment land in Phase A.
"""

from .transcript_io import load_transcript  # noqa: F401
