"""Step 5 — Transcription: audio -> transcript JSON (Segment[]).

Backend is config-swappable (KDS_ASR_BACKEND):
  * groq_whisper  — hosted Groq Whisper (dev default, no GPU fleet needed)
  * collaborator  — placeholder for the GPU-fleet tooling (must emit SCHEMA.md JSON)

Output is written to data/transcripts/<video_id>.json and validated against the
Transcript schema. Long audio is chunked by ffmpeg so it stays under provider
size limits.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from .. import config
from ..schemas import Segment, Transcript

# Groq's audio endpoint accepts large files; we chunk defensively for long rounds.
_CHUNK_SECONDS = 600  # 10 min


def transcribe(
    audio_path: str | Path,
    *,
    source_url: Optional[str] = None,
    title: Optional[str] = None,
    video_id: Optional[str] = None,
    settings: Optional[config.Settings] = None,
) -> Transcript:
    settings = settings or config.get_settings()
    audio_path = Path(audio_path)
    if settings.asr_backend == "groq_whisper":
        segments = _transcribe_groq(audio_path, settings)
    elif settings.asr_backend == "collaborator":
        raise NotImplementedError(
            "collaborator ASR backend not wired yet — provide its invocation/format."
        )
    else:
        raise ValueError(f"Unknown ASR backend: {settings.asr_backend}")

    transcript = Transcript(
        source=source_url,
        metadata={"title": title} if title else None,
        segments=segments,
    )

    if video_id:
        out = config.TRANSCRIPTS_DIR / f"{video_id}.json"
        config.ensure_dirs()
        out.write_text(
            transcript.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
        )
    return transcript


def _audio_duration(path: Path) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, check=True,
        )
        return float(out.stdout.strip())
    except Exception:
        return 0.0


def _split_chunks(path: Path, chunk_seconds: int) -> list[tuple[Path, float]]:
    """Split audio into <=chunk_seconds pieces; return (path, start_offset)."""
    duration = _audio_duration(path)
    if duration <= chunk_seconds:
        return [(path, 0.0)]
    tmpdir = Path(tempfile.mkdtemp(prefix="kds_chunks_"))
    chunks: list[tuple[Path, float]] = []
    start = 0.0
    idx = 0
    while start < duration:
        out = tmpdir / f"chunk_{idx:03d}.mp3"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(path), "-ss", str(start),
             "-t", str(chunk_seconds), "-acodec", "copy", str(out)],
            check=True,
        )
        chunks.append((out, start))
        start += chunk_seconds
        idx += 1
    return chunks


def _transcribe_groq(audio_path: Path, settings: config.Settings) -> list[Segment]:
    from openai import OpenAI

    client = OpenAI(
        base_url=settings.provider_cfg["base_url"],
        api_key=settings.api_key,
    )
    segments: list[Segment] = []
    for chunk_path, offset in _split_chunks(audio_path, _CHUNK_SECONDS):
        with chunk_path.open("rb") as f:
            resp = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=f,
                response_format="verbose_json",
            )
        # verbose_json returns .segments with start/end/text.
        raw_segments = getattr(resp, "segments", None) or []
        if raw_segments:
            for s in raw_segments:
                d = s if isinstance(s, dict) else s.__dict__
                text = (d.get("text") or "").strip()
                if not text:
                    continue
                segments.append(
                    Segment(
                        text=text,
                        start=_num(d.get("start"), offset),
                        end=_num(d.get("end"), offset),
                    )
                )
        else:
            # Fallback: whole-chunk text as a single segment.
            text = (getattr(resp, "text", "") or "").strip()
            if text:
                segments.append(Segment(text=text, start=offset))
    return segments


def _num(v, offset: float):
    return None if v is None else float(v) + offset
