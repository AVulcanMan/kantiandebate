"""Thin client for the OpenCaseList API (api.opencaselist.com/v1).

Auth is a ``caselist_token`` cookie. The token is read from the CASELIST_TOKEN
environment variable, or from secret.txt (a ``CASELIST_TOKEN=...`` line, or a
bare alphanumeric token that isn't an LLM key). Never printed.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Optional

from .. import config

BASE_URL = "https://api.opencaselist.com/v1"


class CaselistError(RuntimeError):
    pass


def get_token() -> Optional[str]:
    import os

    if os.environ.get("CASELIST_TOKEN"):
        return os.environ["CASELIST_TOKEN"]
    secret = config.ROOT / "secret.txt"
    if not secret.exists():
        return None
    bare_candidate = None
    for line in secret.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.upper().startswith("CASELIST_TOKEN="):
            return s.split("=", 1)[1].strip()
        # A bare token that isn't an LLM key (gsk_/sk-) and looks like a session id.
        if not s.startswith(("gsk_", "sk-")) and re.fullmatch(r"[A-Za-z0-9._-]{24,128}", s):
            bare_candidate = bare_candidate or s
    return bare_candidate


def _request(path: str, params: Optional[dict] = None, timeout: float = 30.0):
    token = get_token()
    if not token:
        raise CaselistError(
            "No CASELIST_TOKEN found. Add it to secret.txt (CASELIST_TOKEN=...) "
            "or the environment."
        )
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Cookie": f"caselist_token={token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise CaselistError(f"API {e.code} for {path}: {e.read()[:200]!r}") from e


def list_caselists(archived: bool = False) -> list[dict]:
    return _request("/caselists", {"archived": str(archived).lower()})


def search_shard(query: str, shard: str) -> list[dict]:
    """Call the upstream per-shard search. Returns [] on shard error."""
    try:
        result = _request("/search", {"q": query, "shard": shard})
        return result if isinstance(result, list) else []
    except CaselistError:
        return []


def download_file(path: str, dest_dir, filename: Optional[str] = None):
    """Download a disclosure file (the /download endpoint streams the .docx).

    Saves to dest_dir and returns the written Path. Validates it looks like a
    real Office doc (ZIP 'PK' magic) before keeping it.
    """
    from pathlib import Path

    token = get_token()
    if not token:
        raise CaselistError("No CASELIST_TOKEN found.")
    url = BASE_URL + "/download?" + urllib.parse.urlencode({"path": path})
    req = urllib.request.Request(url, headers={"Cookie": f"caselist_token={token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        raise CaselistError(f"Download {e.code} for {path}: {e.read()[:200]!r}") from e
    if data[:2] != b"PK":
        raise CaselistError(f"Downloaded data for {path!r} is not a valid Office doc.")
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (filename or path.split("/")[-1])
    dest.write_bytes(data)
    return dest


def get_cites(caselist: str, school: str, team: str, side: Optional[str] = None) -> list[dict]:
    params = {"side": side} if side else None
    return _request(
        f"/caselists/{caselist}/schools/{school}/teams/{team}/cites", params
    )


def parse_path(path: str) -> dict:
    """Parse a result path like 'ndtceda25/School/Team#653212'.

    Returns {caselist, school, team, cite_id?}. Raises on malformed input.
    """
    cite_id = None
    body = path.strip().strip("/")
    if "#" in body:
        body, frag = body.split("#", 1)
        if frag.isdigit():
            cite_id = int(frag)
    parts = body.split("/")
    if len(parts) < 3:
        raise CaselistError(
            f"Cannot parse path {path!r}; expected caselist/school/team[#cite_id]."
        )
    return {"caselist": parts[0], "school": parts[1], "team": parts[2], "cite_id": cite_id}


def get_cite_by_path(path: str) -> dict:
    """Fetch the full text of a single cite identified by a result path."""
    p = parse_path(path)
    cites = get_cites(p["caselist"], p["school"], p["team"])
    if p["cite_id"] is not None:
        for c in cites:
            if c.get("cite_id") == p["cite_id"]:
                return c
        raise CaselistError(f"Cite #{p['cite_id']} not found under {path!r}.")
    if not cites:
        raise CaselistError(f"No cites found under {path!r}.")
    return cites[0]
