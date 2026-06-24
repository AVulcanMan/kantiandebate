"""Step 4 — YouTube ingestion: URL -> audio file + metadata.

Downloads audio-only (smallest footprint) via yt-dlp into data/footage/<id>/ and
returns a small metadata dict. Idempotent: re-running on the same URL reuses the
existing download.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .. import config


def _video_id(url: str) -> str:
    """Extract a stable id for foldering without a network call."""
    import re

    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else re.sub(r"[^A-Za-z0-9_-]", "_", url)[-16:]


def fetch_audio(url: str, out_dir: Optional[Path] = None) -> dict:
    """Download audio for a YouTube URL. Returns metadata incl. audio_path."""
    import yt_dlp

    config.ensure_dirs()
    vid = _video_id(url)
    dest = (out_dir or config.FOOTAGE_DIR) / vid
    dest.mkdir(parents=True, exist_ok=True)
    meta_path = dest / "meta.json"

    # Idempotent: reuse a prior successful download.
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("audio_path") and Path(meta["audio_path"]).exists():
            return meta

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(dest / "audio.%(ext)s"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}
        ],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    audio_path = dest / "audio.mp3"
    meta = {
        "video_id": vid,
        "source_url": url,
        "title": info.get("title"),
        "channel": info.get("uploader") or info.get("channel"),
        "duration_seconds": info.get("duration"),
        "audio_path": str(audio_path),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta
