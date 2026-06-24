"""Eval harness: score generator output against rubrics.

Lets you measure whether a prompt edit improved things instead of guessing.
Run `python cli.py eval motion`; edit a prompt under prompts/; rerun; compare.

Scoring (see eval/rubrics.md):
  * type_accuracy — deterministic, via the rule classifier (free).
  * specificity / debatability — an LLM judge (prompts/motion_judge.md).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from . import config
from .corpus.classify import classify
from .generators.base import Generator
from .generators.motion import MotionGenerator
from .prompts import load_prompt

EVAL_DIR = config.ROOT / "eval"


class _MotionScore(BaseModel):
    index: int
    type_correct: bool = False
    specificity: float = 0.0
    debatability: float = 0.0
    note: Optional[str] = None


class _JudgeResult(BaseModel):
    scores: list[_MotionScore]


class MotionJudge(Generator):
    name = "motion_judge"

    def judge(self, motion_type: str, motions: list[str], *, dry_run: bool = False) -> list[_MotionScore]:
        system = load_prompt("motion_judge", motion_type=motion_type)
        listing = "\n".join(f"{i + 1}. {m}" for i, m in enumerate(motions))
        user = f"Requested type: {motion_type}\n\nMOTIONS:\n{listing}\n\nScore each as STRICT JSON."
        data = self._generate_json(system, user, type_tag=motion_type, dry_run=dry_run)
        return self._validate(_JudgeResult, data).scores


def load_cases(path: Optional[Path] = None) -> list[dict]:
    path = path or (EVAL_DIR / "cases" / "motion.jsonl")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _composite(type_acc: float, spec: float, deb: float) -> float:
    # 0-10: type gate weighted 4, specificity 3, debatability 3.
    return round(type_acc * 4 + (spec / 5) * 3 + (deb / 5) * 3, 2)


def eval_motion(cases: Optional[list[dict]] = None, *, pace_seconds: int = 20) -> dict:
    cases = cases or load_cases()
    gen = MotionGenerator()
    judge = MotionJudge()

    per_motion = []
    for ci, case in enumerate(cases):
        mtype = case["type"]
        motions = gen.generate(mtype, n=case.get("n", 3), theme=case.get("theme"))
        texts = [m.motion for m in motions]
        time.sleep(pace_seconds)  # respect TPM between generate and judge
        scores = judge.judge(mtype, texts)
        score_by_idx = {s.index: s for s in scores}

        for i, text in enumerate(texts, start=1):
            s = score_by_idx.get(i)
            rule_type = classify(text)[0]
            type_acc = 1.0 if rule_type == mtype else 0.0
            spec = s.specificity if s else 0.0
            deb = s.debatability if s else 0.0
            per_motion.append(
                {
                    "case": ci,
                    "type": mtype,
                    "theme": case.get("theme"),
                    "motion": text,
                    "rule_type": rule_type,
                    "type_accuracy": type_acc,
                    "specificity": spec,
                    "debatability": deb,
                    "composite": _composite(type_acc, spec, deb),
                    "note": s.note if s else None,
                }
            )
        if ci < len(cases) - 1:
            time.sleep(pace_seconds)

    n = len(per_motion) or 1
    summary = {
        "n_motions": len(per_motion),
        "type_accuracy": round(sum(m["type_accuracy"] for m in per_motion) / n, 3),
        "specificity": round(sum(m["specificity"] for m in per_motion) / n, 2),
        "debatability": round(sum(m["debatability"] for m in per_motion) / n, 2),
        "composite": round(sum(m["composite"] for m in per_motion) / n, 2),
    }
    # Per-type breakdown for the specificity-by-type view.
    by_type = {}
    for t in ("policy", "value", "fact"):
        rows = [m for m in per_motion if m["type"] == t]
        if rows:
            by_type[t] = {
                "specificity": round(sum(r["specificity"] for r in rows) / len(rows), 2),
                "type_accuracy": round(sum(r["type_accuracy"] for r in rows) / len(rows), 3),
            }
    return {"summary": summary, "by_type": by_type, "motions": per_motion}
