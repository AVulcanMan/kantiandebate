"""Append every LLM call to logs/generations.jsonl in a training-ready schema.

This file is the fine-tuning substrate. Each record is one prompt/response pair
plus enough metadata to replay it and (later) build supervised examples. Human
edits/gradings are attached via ``human_edit`` by the drill runner.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from .. import config


def log_generation(
    *,
    generator: str,
    system: str,
    user: str,
    output: str,
    type_tag: Optional[str] = None,
    fewshots: Optional[list[Any]] = None,
    params: Optional[dict] = None,
    human_edit: Optional[str] = None,
    extra: Optional[dict] = None,
    path: Optional[Path] = None,
) -> dict:
    """Write one JSONL record and return it."""
    path = path or config.GENERATIONS_LOG
    path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp": time.time(),
        "iso_time": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "generator": generator,
        "type_tag": type_tag,
        "system": system,
        "user": user,
        "fewshots": fewshots or [],
        "output": output,
        "params": params or {},
        "human_edit": human_edit,
    }
    if extra:
        record["extra"] = extra

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
