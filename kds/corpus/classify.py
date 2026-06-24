"""Rule-based resolution classifier (policy / value / fact).

Refactored from the original top-level ``classify_resolutions.py`` into an
importable, callable function. Fully deterministic — no API calls. The boundary
this encodes is the authoritative one frozen in ``kds.taxonomy`` (notably:
'better than' / 'more harm than good' => fact; 'outweighs' / 'preferable to' =>
value).

Returns (classification, confidence) where classification is one of
'policy' | 'value' | 'fact' and confidence is 'high' | 'medium' | 'low'.
"""

from __future__ import annotations

import re

Classification = tuple[str, str]


def _find(pattern: str, text: str) -> bool:
    return bool(re.search(pattern, text, re.IGNORECASE))


def classify(res: str) -> Classification:
    # Strip INFOSLIDE blocks so they don't pollute keyword matching.
    clean = re.split(r"\bINFO\s*SLIDE\b", str(res), flags=re.IGNORECASE)[0].strip()

    # ── POLICY ────────────────────────────────────────────────────────────────
    if _find(r"\bshould\b", clean):
        return "policy", "high"
    if _find(r"\bTHW\b|\bTH[,.]?\s+(\w[\w\s,.']+,\s+)?W\b", clean):
        return "policy", "medium"
    if _find(r"\bwould\b", clean):
        return "policy", "medium"
    if _find(r"\bTHS\b|\bThis House Supports?\b", clean):
        return "policy", "medium"
    if _find(r"\bThis House [Oo]pposes?\b|\bTHO\b", clean):
        return "policy", "medium"
    if _find(r"\bTH[,.]?\s+will\b|\bThis House will\b", clean):
        return "policy", "medium"

    # ── VALUE ─────────────────────────────────────────────────────────────────
    if _find(r"\bought\b", clean):
        return "value", "high"
    if _find(r"\bTHP\b|\bThis House Prefers?\b", clean):
        return "value", "high"
    if _find(r"\bTHR\b|\bThis House [Rr]egrets?\b|\bThis House [Vv]alues?\b", clean):
        return "value", "high"
    if _find(r"\b(have?|has) (a |moral |legal )?(responsibility|obligation|duty)\b", clean):
        return "value", "medium"

    value_comparison = (
        r"\b(is|are) more important than\b"
        r"|\boutweighs?\b"
        r"|\btakes? precedence over\b"
        r"|\bprioritize[sd]? .{1,40} over\b"
        r"|\bvalues? .{1,40} over\b"
        r"|\bshould be prioritized over\b"
        r"|\bmore valuable than\b"
        r"|\b(is|are) (morally |ethically )?(superior|preferable|more desirable) to\b"
        r"|\b(is|are) preferable to\b"
        r"|\bless important than\b"
        r"|\bdeserves? (more|greater|less) (weight|consideration|priority)\b"
    )
    if _find(value_comparison, clean):
        return "value", "high"

    normative_predicate = (
        r"\b(is|are|was|were) (un)?just(ified)?\b"
        r"|\b(is|are|was|were) (im)?moral\b"
        r"|\b(is|are|was|were) (un)?ethical\b"
        r"|\b(is|are|was|were) (un)?fair(ly)?\b"
        r"|\b(is|are|was|were) (il)?legitimate\b"
        r"|\b(is|are) (in)?equitable\b"
        r"|\b(is|are) virtuous\b"
        r"|\b(is|are) a (human |fundamental |natural |basic )?right\b"
        r"|\b(is|are) (in)?consistent with (human dignity|justice|morality|ethics|democratic values)\b"
        r"|\b(is|are) (morally|ethically) (wrong|right|permissible|impermissible|acceptable|unacceptable|problematic|justified|unjustified)\b"
    )
    if _find(normative_predicate, clean):
        return "value", "high"
    if _find(r"\bthis house (values?|believes? in)\b", clean):
        return "value", "medium"

    # ── FACT ──────────────────────────────────────────────────────────────────
    if _find(r"\bbetter than\b", clean):
        return "fact", "medium"
    if _find(r"\b(does?|did|has?|have) more (harm|good|damage|benefit) than\b", clean):
        return "fact", "high"
    if _find(r"\bmore (harm|good|damage|benefit) than (good|harm|benefit|damage)\b", clean):
        return "fact", "high"

    empirical = (
        r"\b(has|have) (significantly |greatly |largely )?(improved|worsened|increased|decreased|"
        r"reduced|expanded|undermined|strengthened|weakened|damaged|benefited|harmed)\b"
        r"|\b(is|are|was|were) (the )?(primary|main|leading|key|major|biggest|most significant|"
        r"greatest|principal|chief|dominant|fundamental) (cause|driver|factor|source|reason|force|threat)\b"
        r"|\b(is|are) (in)?effective\b"
        r"|\b(is|are) (un)?successful\b"
        r"|\b(is|are) responsible for\b"
        r"|\b(is|are) a (net )?(positive|negative|benefit|cost|threat|risk)\b"
        r"|\bhas (led|resulted|contributed) to\b"
        r"|\bis (growing|declining|rising|falling|increasing|decreasing)\b"
        r"|\bdoes (not )?work\b"
        r"|\b(is|are) (largely|primarily|mostly|generally) (beneficial|harmful|positive|negative|good|bad)\b"
        r"|\bhas been (and will be )?(beneficial|harmful|detrimental|counterproductive|damaging|positive|negative|good|bad|successful|a failure)\b"
        r"|\b(will be|has been) (largely|primarily|mostly|generally|on balance) (beneficial|harmful|positive|negative|good|bad|detrimental)\b"
    )
    if _find(empirical, clean):
        return "fact", "high"
    if _find(r"\bthis house believes?\b", clean):
        return "fact", "medium"
    if _find(r"\b(is|are|was|were)\b", clean):
        return "fact", "medium"

    # Bare declarative (no copula) — fact, low confidence (effectively unlabeled).
    return "fact", "low"
