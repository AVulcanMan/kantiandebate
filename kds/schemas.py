"""Pydantic schemas for KDS.

These models ARE the contract between pipeline stages and the future training
format. Keep them strict and stable. Drill-specific output schemas are stubbed
here and fleshed out as each generator is built.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .taxonomy import MotionType

Confidence = Literal["high", "medium", "low"]


# ── corpus ───────────────────────────────────────────────────────────────────
class Resolution(BaseModel):
    text: str
    motion_type: MotionType
    confidence: Confidence
    season: Optional[str] = None
    tournament: Optional[str] = None
    region: Optional[str] = None
    needs_review: bool = False  # True for low-confidence (effectively unlabeled)

    @field_validator("text")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("resolution text must be non-empty")
        return v


# ── footage pipeline ─────────────────────────────────────────────────────────
class Segment(BaseModel):
    """One contiguous transcript chunk as emitted by ASR / the collaborator."""

    text: str
    speaker: Optional[str] = None
    start: Optional[float] = Field(default=None, description="seconds")
    end: Optional[float] = Field(default=None, description="seconds")
    confidence: Optional[float] = None

    @field_validator("text")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("segment text must be non-empty")
        return v

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, v, info):
        start = info.data.get("start")
        if v is not None and start is not None and v < start:
            raise ValueError("segment end must be >= start")
        return v


class TranscriptMetadata(BaseModel):
    title: Optional[str] = None
    channel: Optional[str] = None
    duration_seconds: Optional[float] = None


class Transcript(BaseModel):
    # Matches data/transcripts/SCHEMA.md: source + metadata + segments.
    source: Optional[str] = None
    metadata: Optional[TranscriptMetadata] = None
    segments: list[Segment]


class ArgumentUnit(BaseModel):
    """A single argument extracted from the transcript: the drill atom.

    This is the canonical 'flow' entry. Drills (refutation, flowing, round
    vision) all consume ArgumentUnit[].
    """

    claim: str
    warrant: Optional[str] = None
    impact: Optional[str] = None
    speaker: Optional[str] = None
    source_quote: Optional[str] = None  # verbatim span from the transcript
    order: Optional[int] = None  # position within the round
    confidence: Confidence = "medium"

    @field_validator("claim")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("argument claim must be non-empty")
        return v

    @property
    def needs_review(self) -> bool:
        return self.confidence == "low"


# ── drill I/O (stubs, expanded per generator in later steps) ──────────────────
class Motion(BaseModel):
    motion: str
    motion_type: MotionType
    rationale: Optional[str] = None
    debatability_note: Optional[str] = None


class MotionList(BaseModel):
    motions: list[Motion]


class RefutationGrade(BaseModel):
    clash_type: Optional[str] = None  # turn | mitigate | outweigh | no-link | link-defense
    score: Optional[float] = None
    what_landed: Optional[str] = None
    what_was_dropped: Optional[str] = None
    model_refutation: Optional[str] = None


class ArgumentList(BaseModel):
    """LLM segmentation output: the extracted flow of a round."""

    arguments: list[ArgumentUnit]


class RefutationPrompt(BaseModel):
    """Drill-mode output: present the argument and ask the user to refute it."""

    prompt: str
    hints: list[str] = []


def _to_str_list(v):
    if v is None:
        return []
    if not isinstance(v, list):
        v = [v]
    return [x if isinstance(x, str) else str(x) for x in v]


def _to_str_dict(v):
    if not isinstance(v, dict):
        return {}
    return {str(k): (x if isinstance(x, str) else str(x)) for k, x in v.items()}


class FlowingResult(BaseModel):
    caught: list[str] = []
    missed: list[str] = []
    mislabeled: list[str] = []
    coverage_score: Optional[float] = None
    notes: Optional[str] = None

    @field_validator("caught", "missed", "mislabeled", mode="before")
    @classmethod
    def _coerce_lists(cls, v):
        return _to_str_list(v)


class RoundVisionResult(BaseModel):
    per_question_grade: dict[str, str] = {}
    model_answer: dict[str, str] = {}
    reveal: Optional[str] = None
    score: Optional[float] = None

    @field_validator("per_question_grade", "model_answer", mode="before")
    @classmethod
    def _coerce_dicts(cls, v):
        return _to_str_dict(v)
