import pytest

from kds import config
from kds.eval import _composite, load_cases
from kds.generators.motion import _type_guidance
from kds.prompts import load_prompt


def test_all_prompt_files_load():
    for name in [
        "motion", "segmentation", "refutation_drill", "refutation_grade",
        "flowing", "round_vision", "motion_judge",
    ]:
        text = load_prompt(name)
        assert text and len(text) > 20


def test_motion_prompt_substitution():
    out = load_prompt(
        "motion", type_definition="DEF", type_guidance="GUIDE",
        motion_type="policy", theme_line="THEME",
    )
    assert "DEF" in out and "GUIDE" in out and "policy" in out
    assert "<<" not in out  # all placeholders resolved


def test_missing_prompt_raises():
    with pytest.raises(FileNotFoundError):
        load_prompt("does_not_exist")


def test_type_guidance_sections():
    assert "specific" in _type_guidance("policy").lower()
    assert _type_guidance("value")
    assert _type_guidance("fact")


def test_config_toml_loaded():
    t = config.load_toml()
    assert t.get("llm", {}).get("provider") in ("groq", "together")
    mc = config.motion_config()
    assert mc["n_fewshots"] >= 1


def test_env_overrides_toml(monkeypatch):
    monkeypatch.setenv("KDS_PROVIDER", "together")
    s = config.Settings()
    assert s.provider == "together"


def test_composite_scoring():
    # perfect: type correct, spec 5, deb 5 -> 10
    assert _composite(1.0, 5, 5) == 10.0
    # wrong type, mediocre -> low
    assert _composite(0.0, 2, 2) < 3


def test_eval_cases_load():
    cases = load_cases()
    assert cases and all("type" in c for c in cases)
