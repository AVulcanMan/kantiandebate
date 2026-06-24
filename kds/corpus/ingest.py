"""Ingest the classified resolution CSV into a clean SQLite corpus.

Reads ``data/parliresolutions_classified.csv``, normalizes columns, deduplicates
on a case/space-normalized key, and writes a ``resolutions`` table to
``data/corpus.sqlite``. Low-confidence rows are flagged ``needs_review`` (the
classifier's "gave up" bucket) rather than trusted as labels.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

from .. import config


def _dedup_key(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).strip().lower())


def build_corpus(
    csv_path: Path | None = None,
    db_path: Path | None = None,
) -> dict:
    csv_path = csv_path or config.CLASSIFIED_CSV
    db_path = db_path or config.CORPUS_DB
    config.ensure_dirs()

    df = pd.read_csv(csv_path)
    df["Resolution"] = df["Resolution"].astype(str).str.strip()

    rows = []
    seen: set[str] = set()
    n_total = 0
    for _, r in df.iterrows():
        text = r["Resolution"]
        if not text or text.lower() == "nan":
            continue
        n_total += 1
        key = _dedup_key(text)
        if key in seen:
            continue
        seen.add(key)

        cls = str(r.get("classification", "") or "").strip().lower()
        conf = str(r.get("classification_confidence", "") or "").strip().lower()
        if cls not in {"policy", "value", "fact"}:
            cls = "fact"  # mirror classifier default
        if conf not in {"high", "medium", "low"}:
            conf = "low"

        rows.append(
            {
                "text": text,
                "class": cls,
                "confidence": conf,
                "season": _clean(r.get("Season")),
                "tournament": _clean(r.get("Tournament")),
                "region": _clean(r.get("Region")),
                "dedup_key": key,
                "needs_review": 1 if conf == "low" else 0,
            }
        )

    db_path.unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE resolutions (
                id INTEGER PRIMARY KEY,
                text TEXT NOT NULL,
                class TEXT NOT NULL,
                confidence TEXT NOT NULL,
                season TEXT,
                tournament TEXT,
                region TEXT,
                dedup_key TEXT UNIQUE,
                needs_review INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO resolutions
                (text, class, confidence, season, tournament, region, dedup_key, needs_review)
            VALUES (:text, :class, :confidence, :season, :tournament, :region, :dedup_key, :needs_review)
            """,
            rows,
        )
        conn.execute("CREATE INDEX idx_class ON resolutions(class)")
        conn.execute("CREATE INDEX idx_conf ON resolutions(confidence)")
        conn.commit()

        counts = dict(
            conn.execute(
                "SELECT class, COUNT(*) FROM resolutions GROUP BY class"
            ).fetchall()
        )
    finally:
        conn.close()

    return {
        "rows_seen": n_total,
        "unique_written": len(rows),
        "by_class": counts,
        "db_path": str(db_path),
    }


def _clean(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s and s.lower() != "nan" else None


if __name__ == "__main__":
    stats = build_corpus()
    print(
        f"Wrote {stats['unique_written']:,} unique resolutions "
        f"(from {stats['rows_seen']:,} rows) to {stats['db_path']}"
    )
    print("By class:", stats["by_class"])
