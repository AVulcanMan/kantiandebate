"""Class-balanced few-shot sampling from the corpus.

The corpus is policy-skewed ~5:1, so naive sampling starves value/fact. These
helpers draw balanced sets for use as generator few-shots.
"""

from __future__ import annotations

import random
import sqlite3
from pathlib import Path

from .. import config

CLASSES = ("policy", "value", "fact")


def _connect(db_path: Path | None) -> sqlite3.Connection:
    db_path = db_path or config.CORPUS_DB
    if not db_path.exists():
        raise FileNotFoundError(
            f"Corpus DB not found at {db_path}. Run `python cli.py ingest` first."
        )
    return sqlite3.connect(db_path)


def sample_by_class(
    motion_type: str,
    n: int = 5,
    min_confidence: str = "high",
    db_path: Path | None = None,
    seed: int | None = None,
) -> list[str]:
    """Return up to ``n`` resolution texts of one class."""
    conf_filter = {
        "high": ("high",),
        "medium": ("high", "medium"),
        "low": ("high", "medium", "low"),
    }[min_confidence]
    placeholders = ",".join("?" for _ in conf_filter)
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            f"""
            SELECT text FROM resolutions
            WHERE class = ? AND confidence IN ({placeholders})
            """,
            (motion_type, *conf_filter),
        ).fetchall()
    finally:
        conn.close()
    texts = [r[0] for r in rows]
    rng = random.Random(seed)
    rng.shuffle(texts)
    return texts[:n]


def balanced_fewshots(
    n_per_class: int = 3,
    min_confidence: str = "high",
    db_path: Path | None = None,
    seed: int | None = None,
) -> dict[str, list[str]]:
    """Return {class: [examples]} balanced across all three classes."""
    return {
        cls: sample_by_class(
            cls, n=n_per_class, min_confidence=min_confidence, db_path=db_path, seed=seed
        )
        for cls in CLASSES
    }
