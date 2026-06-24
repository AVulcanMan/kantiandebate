# KDS — Kantian Debate Society

A content-to-practice pipeline for Parliamentary and Congressional debate. The core feature is
turning real debate footage (YouTube) into typed **refutation / flowing / round-vision drills**. See
the full build plan referenced in the project notes.

## Status: Phase 0 (foundations) complete

- `kds/taxonomy.py` — frozen policy/value/fact definitions + gold examples.
- `kds/corpus/` — rule-based classifier (refactored), CSV → `data/corpus.sqlite` ingest, class-balanced sampler.
- `kds/llm/` — provider-agnostic client (Groq/Together) + training-ready call logging.
- `kds/schemas.py` — pydantic models (`Resolution`, `Segment`, `ArgumentUnit`, `Transcript`).
- `kds/pipeline/transcript_io.py` — transcript JSON loader/validator (contract in `data/transcripts/SCHEMA.md`).

## Setup

```bash
python3 -m pip install -r requirements.txt   # pandas, pydantic, openai, yt-dlp, pytest
```

LLM calls read an API key from the environment (or an untracked `secret.txt` of `KEY=VALUE` lines).
See `.env.example`. Default provider is Groq; Together is a drop-in fallback (`KDS_PROVIDER=together`).
Phase 0 corpus/schema work needs **no** API key — the `openai` import is lazy.

## Usage

```bash
python3 cli.py ingest                                  # build data/corpus.sqlite (~9,622 unique)
python3 cli.py transcript-check data/transcripts/sample_round.json
python3 -m pytest tests/ -q                             # tests

# Footage -> drills (the core)
python3 cli.py pipeline run "<youtube_url>"            # audio -> transcript -> argument flow
python3 cli.py drill refutation --video <id> --arg N --refutation "your refutation"
python3 cli.py drill flowing --video <id>             # interactive
python3 cli.py drill round_vision --video <id>        # interactive

# Motion generator (type-conditioned, optional news grounding)
python3 cli.py generate motion --type value --theme "artificial intelligence" --n 5
python3 cli.py generate motion --type policy --n 5     # no theme
python3 cli.py generate motion --type fact --theme "social media" --news
```

Motion `--type` is `policy|value|fact` (enforced against the frozen taxonomy). `--theme` centers the
motions on a topic and auto-pulls recent headlines (Google News RSS, no key; set `NEWSAPI_KEY` to use
NewsAPI instead). News is cached in `data/news_cache/` for 6h.

## Caselist search (OpenCaseList)

A federated, ranked, filtered search over the OpenCaseList disclosure wiki — fixes the upstream
`/search` being single-shard, unranked, and filterless. Needs a `CASELIST_TOKEN` in `secret.txt`
(the `caselist_token` cookie from opencaselist.com).

```bash
python3 cli.py caselist list                                   # show shards
python3 cli.py caselist search "taiwan deterrence" --event cx --type cite
python3 cli.py caselist search "china econ" --side neg --type file --limit 10
python3 cli.py caselist search "risk of great power war" --event cx --semantic   # LLM re-rank
python3 cli.py caselist open ndtceda25/MissouriState/BaHa#653212                  # full cite text
```

Filters: `--event cx|ld|pf`, `--level hs|college`, `--type cite|file`, `--side aff|neg`,
`--argtype kritik|counterplan|topicality|theory|disad|advantage|plan|framework|case`,
`--school <substr>`, `--team <substr>`, `--limit N`. Side is inferred from speech labels
(1AC/1NC…), filenames, then argument structure (a CP/DA/T is neg, a plan/advantage is aff).
Argument type is detected from the disclosed tagline + snippet header. Results are merged across
matching shards,
**query-expanded** (the full query plus its salient terms, for recall), re-ranked by relevance
(title/snippet term frequency + phrase boost), and side is inferred from filenames.

- `--semantic` adds an LLM re-rank of the top results by *meaning* (demotes superficial keyword
  matches). Prompt is editable at `prompts/caselist_rerank.md`.
- `caselist open <path>` prints a cite's full card text (taglines, authors, quals, cites). Paths come
  from search results (the part after `opencaselist.com/`).

## Editing harness (tune without touching code)

- **Prompts** live in `prompts/*.md` — edit the text, rerun, changes take effect immediately (no
  caching). Placeholders use `<<name>>`. The motion type-specificity rules are in
  `prompts/motion_type_guidance.md` (per-type sections).
- **Tunables** live in `config.toml` (`[llm]` model/temperature, `[motion]` few-shot count, news
  count, …). Environment variables and `secret.txt` still override it.
- **Eval loop** — measure whether a prompt edit helped:
  ```bash
  python3 cli.py eval motion -v
  ```
  Scores generated motions on type-accuracy (rule classifier), specificity, and debatability (LLM
  judge, prompt at `prompts/motion_judge.md`). Edit cases in `eval/cases/motion.jsonl`; rubric in
  `eval/rubrics.md`. Typical loop: run eval → note score → edit a prompt → run eval → compare.

## Conventions

- One provider abstraction (`kds/llm/client.py`); never hardcode a provider in call sites.
- Every LLM call is logged to `logs/generations.jsonl` (the future fine-tuning dataset).
- `data/transcripts/SCHEMA.md` is the contract between transcription and the pipeline.
