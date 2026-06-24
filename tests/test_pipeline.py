from kds.pipeline.segment import _window_segments, review_queue
from kds.pipeline.youtube import _video_id
from kds.generators.round_vision import RoundVisionDrill
from kds.schemas import ArgumentUnit, Segment


def test_window_segments_respects_budget():
    segs = [Segment(text="x" * 100) for _ in range(10)]
    windows = list(_window_segments(segs, max_chars=250))
    # Each window (except possibly trailing) should hold ~2 segments (~202 chars).
    assert all(sum(len(s.text) + 1 for s in w) <= 250 or len(w) == 1 for w in windows)
    # No segments lost.
    assert sum(len(w) for w in windows) == 10


def test_window_single_oversized_segment():
    segs = [Segment(text="y" * 500)]
    windows = list(_window_segments(segs, max_chars=100))
    assert len(windows) == 1 and len(windows[0]) == 1


def test_video_id_extraction():
    assert _video_id("https://youtu.be/FVDvNGpKeso?si=abc") == "FVDvNGpKeso"
    assert _video_id("https://www.youtube.com/watch?v=khhf66NnkjQ") == "khhf66NnkjQ"


def test_review_queue_filters_low():
    args = [
        ArgumentUnit(claim="a", confidence="high"),
        ArgumentUnit(claim="b", confidence="low"),
    ]
    q = review_queue(args)
    assert len(q) == 1 and q[0].claim == "b"


def test_round_vision_snapshot_split():
    args = [ArgumentUnit(claim=f"c{i}", order=i) for i in range(1, 10)]
    before, after = RoundVisionDrill.split_snapshot(args)
    assert before and after
    assert len(before) + len(after) == 9
    assert before[-1].order < after[0].order
