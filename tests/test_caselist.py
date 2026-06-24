import pytest
import kds.caselist.search as S


def test_score_ranks_title_over_snippet():
    hi = {"title": "China Taiwan deterrence", "snippet": "x"}
    lo = {"title": "x", "snippet": "china once"}
    assert S._score("china", hi) > S._score("china", lo)


def test_score_phrase_bonus():
    phrase = {"title": "china taiwan deterrence DA", "snippet": ""}
    scattered = {"title": "china ... deterrence ... taiwan", "snippet": ""}
    assert S._score("china taiwan deterrence", phrase) >= S._score(
        "china taiwan deterrence", scattered
    )


def test_infer_side_from_filename():
    assert S._infer_side({"download_path": "Kansas-JuBo-Neg-1---MoState.docx"}) == "neg"
    assert S._infer_side({"path": "x/Aff/y", "title": "1AC"}) == "aff"
    assert S._infer_side({"title": "Some Case"}) is None


def test_infer_side_word_boundary():
    # "Negation" should not match "neg"; "Affluence" should not match "aff".
    assert S._infer_side({"title": "Negation affluence"}) is None


def test_infer_side_from_speech_label():
    assert S._infer_side({"title": "1AC - Marx"}) == "aff"
    assert S._infer_side({"title": "1NC---OFF"}) == "neg"
    assert S._infer_side({"title": "2AR overview", "snippet": ""}) == "aff"


def test_infer_side_argtype_fallback():
    # No speech label, but a CP is structurally neg; a plan is aff.
    assert S._infer_side({"title": "Rights CP"}, ["counterplan"]) == "neg"
    assert S._infer_side({"title": "The plan"}, ["plan"]) == "aff"
    # Kritik alone is ambiguous (K affs exist) -> no fallback.
    assert S._infer_side({"title": "Racial-Cap"}, ["kritik"]) is None


def test_detect_argtypes():
    assert "counterplan" in S._detect_argtypes({"title": "Rights CP"})
    assert "topicality" in S._detect_argtypes({"title": "T---USFG v1"})
    assert "kritik" in S._detect_argtypes({"title": "1AC - Marx"})
    assert "kritik" in S._detect_argtypes({"title": "Security K"})
    assert "advantage" in S._detect_argtypes({"title": "Adv-- Deterrence"})
    # Snippet noise must not trigger a false positive (title-only detection).
    assert S._detect_argtypes({"title": "Case", "snippet": "marxist theory of capital"}) == ["case"]


def test_select_shards_filters_event_level():
    caselists = [
        {"name": "ndtceda25", "event": "cx", "level": "college"},
        {"name": "hspolicy25", "event": "cx", "level": "hs"},
        {"name": "hsld25", "event": "ld", "level": "hs"},
    ]
    assert S._select_shards(caselists, "cx", None) == ["ndtceda25", "hspolicy25"]
    assert S._select_shards(caselists, "cx", "hs") == ["hspolicy25"]
    assert S._select_shards(caselists, "ld", None) == ["hsld25"]


def test_subqueries_expands_salient_terms():
    subs = S._subqueries("risk of great power war")
    assert subs[0] == "risk of great power war"  # full query first
    assert "great" in subs and "power" in subs
    assert "of" not in subs and "risk" not in subs  # stopwords dropped


def test_subqueries_single_word():
    assert S._subqueries("hegemony") == ["hegemony"]


def test_parse_path():
    from kds.caselist import client

    p = client.parse_path("ndtceda25/MissouriState/BaHa#653212")
    assert p == {"caselist": "ndtceda25", "school": "MissouriState", "team": "BaHa", "cite_id": 653212}
    p2 = client.parse_path("hsld25/School/Team")
    assert p2["cite_id"] is None


def test_parse_path_malformed():
    from kds.caselist import client

    with pytest.raises(client.CaselistError):
        client.parse_path("justone")


def test_grab_dedupe_by_team():
    from kds.caselist.grab import _dedupe_by_team

    def mk(team):
        return S.Result(score=1, type="file", side="aff", caselist="cx", school="X",
                        team=team, title="t", snippet="s", path="p", download_path="d", url="u")
    out = _dedupe_by_team([mk("A"), mk("A"), mk("B")])
    assert [r.team for r in out] == ["A", "B"]


def test_token_loader_skips_llm_key(tmp_path, monkeypatch):
    from kds.caselist import client

    secret = tmp_path / "secret.txt"
    secret.write_text("gsk_someGroqKey1234567890\ndf5018abc1234567890abcdef12345678\n")
    monkeypatch.setattr(client.config, "ROOT", tmp_path)
    monkeypatch.delenv("CASELIST_TOKEN", raising=False)
    tok = client.get_token()
    assert tok and not tok.startswith("gsk_")
