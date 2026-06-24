"""Load and validate transcript JSON into the Segment schema.

This is the contract boundary between the collaborator's transcription tooling
(or the hosted ASR fallback) and the KDS pipeline. See
``data/transcripts/SCHEMA.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..schemas import Transcript


def load_transcript(path: str | Path) -> Transcript:
    """Read a transcript JSON file and validate it into a Transcript model."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return Transcript.model_validate(data)
