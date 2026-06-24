"""Persistence for extracted flows and drill runs.

Argument units (per video) and drill runs are stored in corpus.sqlite alongside
the resolutions. Drill runs (including any human edit/grade) double as training
data and mirror the JSONL generation log.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

from . import config
from .schemas import ArgumentUnit


def _connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    db_path = db_path or config.CORPUS_DB
    config.ensure_dirs()
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS arguments (
            id INTEGER PRIMARY KEY,
            video_id TEXT, ord INTEGER, claim TEXT, warrant TEXT, impact TEXT,
            speaker TEXT, source_quote TEXT, confidence TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS drill_runs (
            id INTEGER PRIMARY KEY,
            ts REAL, drill TEXT, video_id TEXT, arg_ord INTEGER,
            user_input TEXT, result_json TEXT, human_edit TEXT
        )"""
    )
    return conn


def save_arguments(video_id: str, args: list[ArgumentUnit], db_path: Optional[Path] = None) -> None:
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM arguments WHERE video_id = ?", (video_id,))
        conn.executemany(
            """INSERT INTO arguments
               (video_id, ord, claim, warrant, impact, speaker, source_quote, confidence)
               VALUES (?,?,?,?,?,?,?,?)""",
            [
                (video_id, a.order, a.claim, a.warrant, a.impact, a.speaker,
                 a.source_quote, a.confidence)
                for a in args
            ],
        )
        conn.commit()
    finally:
        conn.close()


def load_arguments(video_id: str, db_path: Optional[Path] = None) -> list[ArgumentUnit]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """SELECT ord, claim, warrant, impact, speaker, source_quote, confidence
               FROM arguments WHERE video_id = ? ORDER BY ord""",
            (video_id,),
        ).fetchall()
    finally:
        conn.close()
    return [
        ArgumentUnit(
            order=r[0], claim=r[1], warrant=r[2], impact=r[3], speaker=r[4],
            source_quote=r[5], confidence=r[6] or "medium",
        )
        for r in rows
    ]


def save_run(
    drill: str,
    video_id: str,
    arg_ord: Optional[int],
    user_input: str,
    result: dict,
    human_edit: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> int:
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """INSERT INTO drill_runs (ts, drill, video_id, arg_ord, user_input, result_json, human_edit)
               VALUES (?,?,?,?,?,?,?)""",
            (time.time(), drill, video_id, arg_ord, user_input, json.dumps(result), human_edit),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()
