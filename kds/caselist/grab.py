"""One-shot "find and download": search -> confirm -> download.

Automates the manual process of finding real arguments (e.g. "3 aff settler
colonialism kritiks") and saving the files: it searches broadly, optionally
uses an LLM to confirm each candidate is genuinely the requested argument
(reading snippets, not just filenames), dedupes by team, and downloads the top N
that actually have a file, skipping any that 404.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from ..generators.base import Generator
from ..prompts import load_prompt
from . import client
from .search import Result, search


class _Cand(BaseModel):
    index: int
    relevant: bool = False
    score: float = 0.0
    why: Optional[str] = None


class _Judged(BaseModel):
    results: list[_Cand]


class GrabJudge(Generator):
    name = "caselist_grab"

    def judge(self, want: str, results: list[Result], *, dry_run: bool = False) -> list[_Cand]:
        listing = "\n".join(
            f"{i + 1}. {r.team} — {' '.join(r.snippet.split())[:220]}"
            for i, r in enumerate(results)
        )
        system = load_prompt("caselist_grab", want=want)
        user = f"CANDIDATES:\n{listing}\n\nReturn STRICT JSON now."
        data = self._generate_json(system, user, type_tag="grab", max_tokens=1200, dry_run=dry_run)
        return self._validate(_Judged, data).results


def _dedupe_by_team(results: list[Result]) -> list[Result]:
    seen, out = set(), []
    for r in results:
        key = (r.caselist, r.team)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def grab(
    query: str,
    *,
    n: int = 3,
    dest: str = "downloads",
    side: Optional[str] = None,
    argtype: Optional[str] = None,
    event: Optional[str] = None,
    level: Optional[str] = None,
    confirm: bool = True,
    pool: int = 30,
) -> dict:
    """Find and download up to n files matching the request.

    Returns {downloaded: [(team, path)], considered: int, skipped: [(team, reason)]}.
    """
    # 1) Gather candidate files (federated + query-expanded inside search()).
    raw = search(query, event=event, level=level, type="file", side=side, argtype=None, limit=pool)
    candidates = [r for r in _dedupe_by_team(raw) if r.download_path]

    # 2) Confirm topic + argument type. LLM if available, else keyword fallback.
    descriptor = " ".join(p for p in (side, argtype) if p) or "argument"
    want = f"{descriptor} about {query}"

    ranked: list[tuple[float, Result, Optional[str]]] = []
    if confirm and candidates:
        try:
            judged = GrabJudge().judge(want, candidates)
            by_idx = {j.index: j for j in judged}
            for i, r in enumerate(candidates, start=1):
                j = by_idx.get(i)
                if j and j.relevant:
                    ranked.append((j.score, r, j.why))
        except Exception:
            confirm = False  # fall back below
    if not confirm or not ranked:
        # Keyword fallback: rely on the search relevance score.
        ranked = [(r.score, r, None) for r in candidates]
    ranked.sort(key=lambda x: x[0], reverse=True)

    # 3) Download until n succeed.
    dest_dir = Path(dest)
    downloaded, skipped = [], []
    for score, r, why in ranked:
        if len(downloaded) >= n:
            break
        safe = r.team.replace(" ", "") + "-" + (r.download_path.split("/")[-1])
        try:
            p = client.download_file(r.download_path, dest_dir, filename=safe)
            downloaded.append({"team": r.team, "file": str(p), "why": why, "score": score})
        except Exception as e:
            skipped.append({"team": r.team, "reason": str(e)[:80]})

    return {
        "downloaded": downloaded,
        "considered": len(candidates),
        "skipped": skipped,
        "want": want,
    }
