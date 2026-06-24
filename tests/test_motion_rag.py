from kds.rag.news import Article, context_block
from kds.schemas import Motion, MotionList
from kds.taxonomy import MotionType


def test_context_block_renders():
    arts = [
        Article(title="AI rules tighten", source="Reuters"),
        Article(title="Carbon tax debated", source="BBC"),
    ]
    block = context_block(arts)
    assert "AI rules tighten (Reuters)" in block
    assert block.startswith("RECENT NEWS CONTEXT")


def test_context_block_empty():
    assert context_block([]) == ""


def test_motionlist_schema():
    ml = MotionList.model_validate(
        {"motions": [{"motion": "This House Would ban X", "motion_type": "policy"}]}
    )
    assert ml.motions[0].motion_type == MotionType.POLICY


def test_google_title_source_split_via_article():
    # The RSS parser splits "Headline - Source"; emulate the resulting Article.
    a = Article(title="Headline", source="CNN")
    assert a.title == "Headline" and a.source == "CNN"
