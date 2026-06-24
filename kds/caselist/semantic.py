"""LLM semantic re-ranking for caselist search results.

Keyword ranking finds candidates; this reorders the top of that list by meaning,
so a query like "great power war" surfaces China/Taiwan deterrence cards even
when they don't contain those exact words.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from ..generators.base import Generator
from ..prompts import load_prompt


class _Rank(BaseModel):
    index: int
    score: float = 0.0
    why: Optional[str] = None


class _Ranking(BaseModel):
    ranking: list[_Rank]


class SemanticRanker(Generator):
    name = "caselist_rerank"

    def rerank(self, query: str, results: list, top_k: int = 15, *, dry_run: bool = False):
        """Re-rank the first top_k results by semantic relevance to the query.

        Mutates nothing; returns a new list (reranked head + untouched tail).
        """
        head = results[:top_k]
        tail = results[top_k:]
        if not head:
            return results

        listing = "\n".join(
            f"{i + 1}. {r.title} — {' '.join(r.snippet.split())[:200]}"
            for i, r in enumerate(head)
        )
        system = load_prompt("caselist_rerank", query=query)
        user = f"CANDIDATES:\n{listing}\n\nReturn STRICT JSON ranking now."
        data = self._generate_json(
            system, user, type_tag="rerank", max_tokens=1024, dry_run=dry_run
        )
        ranking = self._validate(_Ranking, data).ranking

        score_by_idx = {r.index: r.score for r in ranking}
        why_by_idx = {r.index: r.why for r in ranking}
        # Attach semantic scores; fall back to keyword score for any omitted.
        for i, r in enumerate(head, start=1):
            r.semantic_score = score_by_idx.get(i)
            r.semantic_why = why_by_idx.get(i)
        head.sort(
            key=lambda r: (r.semantic_score if r.semantic_score is not None else -1),
            reverse=True,
        )
        return head + tail
