import sqlite3

from kds import config
from kds.corpus.ingest import build_corpus
from kds.corpus.sample import balanced_fewshots
from kds.llm.client import LLMClient
from kds.llm.logging import log_generation


def test_build_corpus_dedup(tmp_path):
    db = tmp_path / "corpus.sqlite"
    stats = build_corpus(db_path=db)
    # Expect ~9,649 unique resolutions from the classified CSV.
    assert 9000 <= stats["unique_written"] <= 9870
    assert stats["unique_written"] <= stats["rows_seen"]
    assert set(stats["by_class"]) <= {"policy", "value", "fact"}

    conn = sqlite3.connect(db)
    try:
        # dedup_key is unique -> no duplicate keys.
        total = conn.execute("SELECT COUNT(*) FROM resolutions").fetchone()[0]
        distinct = conn.execute(
            "SELECT COUNT(DISTINCT dedup_key) FROM resolutions"
        ).fetchone()[0]
        assert total == distinct == stats["unique_written"]
    finally:
        conn.close()


def test_balanced_fewshots(tmp_path):
    db = tmp_path / "corpus.sqlite"
    build_corpus(db_path=db)
    shots = balanced_fewshots(n_per_class=3, db_path=db, seed=1)
    assert set(shots) == {"policy", "value", "fact"}
    for cls, examples in shots.items():
        assert len(examples) == 3, cls


def test_llm_dry_run_logs(tmp_path, monkeypatch):
    log_path = tmp_path / "generations.jsonl"
    monkeypatch.setattr(config, "GENERATIONS_LOG", log_path)

    client = LLMClient()
    out = client.chat(
        "You are a test.", "Say hello.", generator="unit_test", dry_run=True
    )
    assert "DRY_RUN" in out
    # A well-formed JSONL record was written.
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    import json

    rec = json.loads(lines[0])
    assert rec["generator"] == "unit_test"
    assert rec["params"]["dry_run"] is True
    assert rec["system"] and rec["user"]


def test_build_messages_includes_fewshots():
    client = LLMClient()
    msgs = client.build_messages(
        "sys", "final user", fewshots=[("ex in", "ex out")]
    )
    assert msgs[0]["role"] == "system"
    assert msgs[-1]["content"] == "final user"
    assert any(m["role"] == "assistant" for m in msgs)


def test_log_generation_direct(tmp_path):
    p = tmp_path / "gen.jsonl"
    rec = log_generation(
        generator="g", system="s", user="u", output="o", type_tag="policy", path=p
    )
    assert rec["type_tag"] == "policy"
    assert p.exists()
