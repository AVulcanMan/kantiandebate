"""Recency retriever for motion generation.

Default source is Google News RSS (no API key, theme-searchable, recent). If a
NEWSAPI_KEY is present in the environment, NewsAPI is used instead as a richer
source. Results are cached to data/news_cache/ for a few hours so repeated
generations don't re-fetch.

This is the "R" in RAG: the news search itself does the retrieval (keyword/theme
relevance), so no separate vector store is needed at this stage.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from .. import config

_CACHE_DIR = config.DATA_DIR / "news_cache"
_CACHE_TTL = 6 * 3600  # 6 hours
_UA = "Mozilla/5.0 (KDS news retriever)"


@dataclass
class Article:
    title: str
    source: Optional[str] = None
    published: Optional[str] = None
    url: Optional[str] = None
    snippet: Optional[str] = None


def fetch_headlines(
    theme: Optional[str] = None, n: int = 8, use_cache: bool = True
) -> list[Article]:
    """Return up to n recent articles for a theme (or general world news)."""
    key = hashlib.sha1(f"{theme}|{n}".encode()).hexdigest()[:16]
    cache_path = _CACHE_DIR / f"{key}.json"
    if use_cache and _fresh(cache_path):
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return [Article(**a) for a in data["articles"]]

    if os.environ.get("NEWSAPI_KEY"):
        articles = _fetch_newsapi(theme, n)
    else:
        articles = _fetch_google_rss(theme, n)

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"ts": time.time(), "articles": [asdict(a) for a in articles]}),
        encoding="utf-8",
    )
    return articles


def _fresh(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return time.time() - json.loads(path.read_text())["ts"] < _CACHE_TTL
    except Exception:
        return False


def _fetch_google_rss(theme: Optional[str], n: int) -> list[Article]:
    if theme:
        q = urllib.parse.quote(theme)
        url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    else:
        url = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    raw = urllib.request.urlopen(req, timeout=20).read()
    root = ET.fromstring(raw)
    out: list[Article] = []
    for item in root.findall(".//item")[:n]:
        title = (item.findtext("title") or "").strip()
        # Google News titles are usually "Headline - Source".
        source = None
        src_el = item.find("source")
        if src_el is not None and src_el.text:
            source = src_el.text.strip()
        elif " - " in title:
            title, source = title.rsplit(" - ", 1)
        out.append(
            Article(
                title=title,
                source=source,
                published=(item.findtext("pubDate") or "").strip() or None,
                url=(item.findtext("link") or "").strip() or None,
            )
        )
    return out


def _fetch_newsapi(theme: Optional[str], n: int) -> list[Article]:
    base = "https://newsapi.org/v2/"
    params = {"pageSize": n, "language": "en", "apiKey": os.environ["NEWSAPI_KEY"]}
    if theme:
        endpoint = "everything"
        params.update({"q": theme, "sortBy": "publishedAt"})
    else:
        endpoint = "top-headlines"
        params["country"] = "us"
    url = base + endpoint + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    data = json.loads(urllib.request.urlopen(req, timeout=20).read())
    out = []
    for a in data.get("articles", [])[:n]:
        out.append(
            Article(
                title=a.get("title") or "",
                source=(a.get("source") or {}).get("name"),
                published=a.get("publishedAt"),
                url=a.get("url"),
                snippet=a.get("description"),
            )
        )
    return out


def context_block(articles: list[Article]) -> str:
    """Render articles as a compact grounding block for a prompt."""
    if not articles:
        return ""
    lines = ["RECENT NEWS CONTEXT (for timeliness; do not cite verbatim):"]
    for a in articles:
        src = f" ({a.source})" if a.source else ""
        lines.append(f"- {a.title}{src}")
    return "\n".join(lines)
