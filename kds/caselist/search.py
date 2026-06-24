"""Federated, ranked, filtered search over OpenCaseList.

Improves on the upstream /search (single-shard, unranked, no filters) by:
  * fanning out across all relevant shards in parallel,
  * re-ranking merged results by query relevance (term frequency + phrase boost),
  * inferring side (aff/neg) from filenames/titles,
  * supporting filters: event, level, type (cite/file), side, school, team.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

from . import client

# event codes used by the API: cx (policy), ld, pf.
_SIDE_RE = re.compile(r"(?<![A-Za-z])(aff|neg)(?![A-Za-z])", re.IGNORECASE)
# Speech labels are a strong side signal: 1AC/2AC/1AR/2AR = aff, 1NC/2NC/1NR/2NR = neg.
_AFF_SPEECH = re.compile(r"(?<![A-Za-z0-9])[12]A[CR](?![A-Za-z])")
_NEG_SPEECH = re.compile(r"(?<![A-Za-z0-9])[12]N[CR](?![A-Za-z])")

# Argument-type detection over the tagline/TITLE (titles are the disclosed arg
# label; snippets are body text and cause false positives). Order = priority for
# the primary label. Abbreviations are matched case-sensitively where lowercase
# would be ambiguous (T, CP, DA, K).
_KRITIK_NAMES = (
    r"cap(?:italism)?|marx|neolib|security|afropess\w*|antiblack\w*|settler|set\s?col|"
    r"psychoanalysis|baudrillard|biopolitic\w*|necropolitic\w*|fem(?:inism)?|queer|"
    r"disab\w*|orientalism|militaris\w*|borders|wilderson|nietzsche|deleuze|"
    r"colonial\w*|abolition|warming\s?rep|model\s?minority"
)
_ARG_PATTERNS: list[tuple[str, "re.Pattern"]] = [
    ("topicality", re.compile(r"\bTopicality\b|(?<![A-Za-z])T(?:\b|-|—|\s*-)")),
    ("theory", re.compile(r"\b(theory|condo|conditionality|severance|intrinsicness|RVI)\b", re.I)),
    ("counterplan", re.compile(r"\bcounter-?plan\b|(?<![A-Za-z])CP(?![A-Za-z])", re.I)),
    ("kritik", re.compile(r"\bkritiks?\b|(?<![A-Za-z])K(?![A-Za-z])|\b(?:" + _KRITIK_NAMES + r")\b", re.I)),
    ("framework", re.compile(r"\bframework\b|(?<![A-Za-z])F/?W(?![A-Za-z])|role of the ballot|\bROB\b", re.I)),
    ("disad", re.compile(r"\bdisad\w*\b|(?<![A-Za-z])DA(?![A-Za-z])", re.I)),
    ("advantage", re.compile(r"\bAdv(?:antage)?\b", re.I)),
    ("plan", re.compile(r"(?<!counter)(?<!counter-)\bplan\b|(?<![A-Za-z])P(?=---)", re.I)),
    ("case", re.compile(r"(?<![A-Za-z])case\b", re.I)),
]
ARG_CHOICES = [name for name, _ in _ARG_PATTERNS]


# Conservative patterns safe to run against the snippet header (no prose-common
# tokens like standalone K/T or kritik name lists).
_SNIPPET_PATTERNS: list[tuple[str, "re.Pattern"]] = [
    ("counterplan", re.compile(r"\bcounter-?plan\b|(?<![A-Za-z])CP(?![A-Za-z])", re.I)),
    ("topicality", re.compile(r"\bTopicality\b|(?<![A-Za-z])T---")),
    ("kritik", re.compile(r"\bkritiks?\b", re.I)),
    ("disad", re.compile(r"\bdisad\w*\b|(?<![A-Za-z])DA(?![A-Za-z])", re.I)),
    ("theory", re.compile(r"\b(condo|conditionality|severance)\b", re.I)),
]


def _detect_argtypes(r: dict) -> list[str]:
    """Detect argument type(s) from the title, plus the snippet header.

    Titles are the disclosed tagline (high precision). Many blocks are titled
    generically ("1NC", "Off"), so we also scan the first ~90 chars of the
    snippet — the argument header — with a conservative pattern set.
    """
    title = r.get("title") or ""
    found = [name for name, pat in _ARG_PATTERNS if pat.search(title)]
    head = (r.get("snippet") or "")[:90]
    for name, pat in _SNIPPET_PATTERNS:
        if name not in found and pat.search(head):
            found.append(name)
    return found

_STOP = {
    "the", "a", "an", "of", "to", "in", "on", "and", "or", "for", "is", "are",
    "be", "by", "with", "risk", "good", "bad", "vs", "over",
}


def _subqueries(query: str, max_terms: int = 4) -> list[str]:
    """Full query plus its most salient single terms, to widen recall.

    The upstream search is narrow on multi-word queries; searching key terms too
    and unioning the results gives the ranker (keyword or semantic) more to work
    with.
    """
    terms = [t for t in re.findall(r"[A-Za-z]+", query.lower()) if len(t) >= 4 and t not in _STOP]
    # Longest-first as a cheap salience proxy; dedupe preserving order.
    seen, salient = set(), []
    for t in sorted(terms, key=len, reverse=True):
        if t not in seen:
            seen.add(t)
            salient.append(t)
    subs = [query] + salient[:max_terms]
    # Dedupe (a one-word query equals its own term).
    out = []
    for s in subs:
        if s not in out:
            out.append(s)
    return out


@dataclass
class Result:
    score: float
    type: str
    side: Optional[str]
    caselist: str
    school: str
    team: str
    title: str
    snippet: str
    path: str
    download_path: Optional[str]
    url: str
    argtypes: list[str] = None
    semantic_score: Optional[float] = None
    semantic_why: Optional[str] = None


# Structurally side-locked argument types (used only as a fallback signal).
_NEG_ARGS = {"counterplan", "disad", "topicality"}
_AFF_ARGS = {"plan", "advantage"}


def _infer_side(r: dict, argtypes: Optional[list[str]] = None) -> Optional[str]:
    # 1) Speech labels in title/snippet are the strongest signal (esp. for cites).
    text = f"{r.get('title') or ''}\n{r.get('snippet') or ''}"
    aff = bool(_AFF_SPEECH.search(text))
    neg = bool(_NEG_SPEECH.search(text))
    if aff and not neg:
        return "aff"
    if neg and not aff:
        return "neg"
    # 2) Explicit Aff/Neg in the filename or path (strong signal for files).
    for field in (r.get("download_path"), r.get("path"), r.get("title")):
        if not field:
            continue
        m = _SIDE_RE.search(field)
        if m:
            return m.group(1).lower()
    # 3) Fallback: a CP/DA/T is structurally neg; a plan/advantage is aff.
    if argtypes:
        s = set(argtypes)
        if s & _NEG_ARGS and not (s & _AFF_ARGS):
            return "neg"
        if s & _AFF_ARGS and not (s & _NEG_ARGS):
            return "aff"
    return None


def _score(query: str, r: dict) -> float:
    terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 1]
    if not terms:
        return 0.0
    title = (r.get("title") or "").lower()
    snippet = (r.get("snippet") or "").lower()
    score = 0.0
    for t in terms:
        score += title.count(t) * 3.0 + snippet.count(t) * 1.0
    # Phrase bonus when the full query appears verbatim.
    q = query.lower().strip()
    if q in title:
        score += 6.0
    elif q in snippet:
        score += 3.0
    # Coverage bonus: reward results matching more distinct terms.
    matched = sum(1 for t in set(terms) if t in title or t in snippet)
    score += matched * 1.5
    return score


def _select_shards(
    caselists: list[dict], event: Optional[str], level: Optional[str]
) -> list[str]:
    shards = []
    for c in caselists:
        if event and c.get("event") != event:
            continue
        if level and c.get("level") != level:
            continue
        shards.append(c["name"])
    return shards


def search(
    query: str,
    *,
    event: Optional[str] = None,      # cx | ld | pf
    level: Optional[str] = None,      # hs | college
    type: Optional[str] = None,       # cite | file
    side: Optional[str] = None,       # aff | neg
    argtype: Optional[str] = None,    # kritik | counterplan | topicality | ...
    school: Optional[str] = None,     # substring
    team: Optional[str] = None,       # substring
    limit: int = 25,
    semantic: bool = False,           # LLM re-rank the top results by meaning
) -> list[Result]:
    caselists = client.list_caselists()
    shards = _select_shards(caselists, event, level)
    if not shards:
        return []

    # Fan out across (shard x subquery) in parallel, then union by path.
    subqueries = _subqueries(query)
    jobs = [(s, q) for s in shards for q in subqueries]
    with ThreadPoolExecutor(max_workers=8) as ex:
        raw_lists = list(ex.map(lambda j: client.search_shard(j[1], j[0]), jobs))
    seen_paths: set[str] = set()
    raw = []
    for sub in raw_lists:
        for r in sub:
            key = r.get("path") or id(r)
            if key in seen_paths:
                continue
            seen_paths.add(key)
            raw.append(r)

    results: list[Result] = []
    for r in raw:
        rtype = r.get("type") or ""
        if type and rtype != type:
            continue
        argtypes = _detect_argtypes(r)
        if argtype and argtype not in argtypes:
            continue
        inferred = _infer_side(r, argtypes)
        if side and inferred != side.lower():
            continue
        if school and school.lower() not in (r.get("school_display_name") or r.get("school") or "").lower():
            continue
        if team and team.lower() not in (r.get("team_display_name") or r.get("team") or "").lower():
            continue
        path = r.get("path") or ""
        results.append(
            Result(
                score=_score(query, r),
                type=rtype,
                side=inferred,
                caselist=r.get("caselist_display_name") or r.get("caselist") or "",
                school=r.get("school_display_name") or r.get("school") or "",
                team=r.get("team_display_name") or r.get("team") or "",
                title=r.get("title") or "",
                snippet=(r.get("snippet") or "").strip(),
                path=path,
                download_path=r.get("download_path"),
                url=f"https://opencaselist.com/{path}" if path else "",
                argtypes=argtypes,
            )
        )

    results.sort(key=lambda x: x.score, reverse=True)
    results = results[:limit]

    if semantic and results:
        # Lazy import: keyword search must not require the LLM stack.
        from .semantic import SemanticRanker

        results = SemanticRanker().rerank(query, results, top_k=min(15, len(results)))
    return results
