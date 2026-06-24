import json

import pytest
from pydantic import ValidationError

from kds import config
from kds.pipeline.transcript_io import load_transcript
from kds.schemas import ArgumentUnit, Segment, Transcript


def test_segment_requires_text():
    with pytest.raises(ValidationError):
        Segment(text="   ")


def test_segment_end_before_start_rejected():
    with pytest.raises(ValidationError):
        Segment(text="hi", start=10.0, end=5.0)


def test_segment_minimal_ok():
    s = Segment(text="Climate change is real.")
    assert s.speaker is None and s.start is None


def test_argument_unit_needs_review_flag():
    a = ArgumentUnit(claim="Subsidies distort markets.", confidence="low")
    assert a.needs_review is True
    b = ArgumentUnit(claim="Subsidies distort markets.", confidence="high")
    assert b.needs_review is False


def test_sample_transcript_parses():
    t = load_transcript(config.TRANSCRIPTS_DIR / "sample_round.json")
    assert isinstance(t, Transcript)
    assert len(t.segments) >= 3
    assert all(seg.text.strip() for seg in t.segments)


def test_transcript_roundtrip_validation():
    raw = json.loads(
        (config.TRANSCRIPTS_DIR / "sample_round.json").read_text(encoding="utf-8")
    )
    Transcript.model_validate(raw)
