"""
Classify parliamentary debate resolutions as policy / value / fact.
Fully rule-based — no API calls required.
"""

import re
import pandas as pd

# ── load ────────────────────────────────────────────────────────────────────
df = pd.read_csv(
    "data/parliresolutions.csv",
    encoding="utf-16",
    sep="\t",
    header=1,
)

resolutions = df["Resolution"].astype(str).str.strip()
print(f"Loaded {len(resolutions):,} rows.\n")

# ── helper ───────────────────────────────────────────────────────────────────
def find(pattern, text):
    return bool(re.search(pattern, text, re.IGNORECASE))

# ── rule engine ──────────────────────────────────────────────────────────────
# Returns (classification, confidence)

def classify(res: str):
    # Strip INFOSIDE blocks so they don't pollute keyword matching
    clean = re.split(r'\bINFO\s*SLIDE\b', res, flags=re.IGNORECASE)[0].strip()

    # ── POLICY ───────────────────────────────────────────────────────────────
    # "should" anywhere → policy (highest priority)
    if find(r"\bshould\b", clean):
        return "policy", "high"

    # Parliamentary abbreviations for "This House Would"
    # THW, TH … W, TH, as [actor], W
    if find(r"\bTHW\b|\bTH[,.]?\s+(\w[\w\s,.']+,\s+)?W\b", clean):
        return "policy", "medium"

    # Parliamentary "This House Would / would" directive
    if find(r"\bwould\b", clean):
        return "policy", "medium"

    # THS = This House Supports → policy-flavoured
    if find(r"\bTHS\b|\bThis House Supports?\b", clean):
        return "policy", "medium"

    # "This House opposes" → policy-flavoured (opposing a practice/policy)
    if find(r"\bThis House [Oo]pposes?\b|\bTHO\b", clean):
        return "policy", "medium"

    # "TH will" / "This House will" → policy
    if find(r"\bTH[,.]?\s+will\b|\bThis House will\b", clean):
        return "policy", "medium"

    # ── VALUE ────────────────────────────────────────────────────────────────
    # "ought" (classic LD-style value motion)
    if find(r"\bought\b", clean):
        return "value", "high"

    # THP = This House Prefers → value (prefers X over Y)
    if find(r"\bTHP\b|\bThis House Prefers?\b", clean):
        return "value", "high"

    # THR = This House Regrets → value (normative judgement)
    if find(r"\bTHR\b|\bThis House [Rr]egrets?\b|\bThis House [Vv]alues?\b", clean):
        return "value", "high"

    # "has a responsibility to" / "have moral obligations" → value
    if find(r"\b(have?|has) (a |moral |legal )?(responsibility|obligation|duty)\b", clean):
        return "value", "medium"

    # Explicit comparative value phrases
    VALUE_COMPARISON = (
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
    if find(VALUE_COMPARISON, clean):
        return "value", "high"

    # Normative/ethical predicates applied to abstract actions or policies
    # e.g. "X is just", "X is immoral", "X is legitimate"
    NORMATIVE_PREDICATE = (
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
    if find(NORMATIVE_PREDICATE, clean):
        return "value", "high"

    # "This house values/believes in X" patterns (abstract normative claim)
    if find(r"\bthis house (values?|believes? in)\b", clean):
        return "value", "medium"

    # ── FACT ─────────────────────────────────────────────────────────────────
    # "better than" — examples in data are all fact-style comparisons
    if find(r"\bbetter than\b", clean):
        return "fact", "medium"

    # "more/less [adj] than" comparing concrete outcomes
    if find(r"\b(does?|did|has?|have) more (harm|good|damage|benefit) than\b", clean):
        return "fact", "high"
    if find(r"\bmore (harm|good|damage|benefit) than (good|harm|benefit|damage)\b", clean):
        return "fact", "high"

    # Empirical/descriptive assertions
    EMPIRICAL = (
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
    if find(EMPIRICAL, clean):
        return "fact", "high"

    # "This house believes (that) [declarative]" — treat as fact unless caught above
    if find(r"\bthis house believes?\b", clean):
        return "fact", "medium"

    # "X is/are Y" declarative — default to fact, medium confidence
    if find(r"\b(is|are|was|were)\b", clean):
        return "fact", "medium"

    # Bare declarative (no copula) — fact, low confidence
    return "fact", "low"

# ── classify all rows ────────────────────────────────────────────────────────
results = [classify(r) for r in resolutions]
classifications = [r[0] for r in results]
confidences    = [r[1] for r in results]

# ── write output ──────────────────────────────────────────────────────────────
df["classification"] = classifications
df["classification_confidence"] = confidences

out_path = "data/parliresolutions_classified.csv"
df.to_csv(out_path, index=False, encoding="utf-8")
print(f"Written to {out_path}\n")

# ── summary ───────────────────────────────────────────────────────────────────
print("=== Classification summary ===")
counts = df["classification"].value_counts()
for label in ["policy", "value", "fact"]:
    print(f"  {label:8s}: {counts.get(label, 0):6,}")

print()
print("=== Confidence breakdown ===")
conf_counts = df["classification_confidence"].value_counts()
for level in ["high", "medium", "low"]:
    print(f"  {level:6s}: {conf_counts.get(level, 0):6,}")

# ── spot-check sample ─────────────────────────────────────────────────────────
print("\n=== Sample classifications ===")
sample = df[["Resolution", "classification", "classification_confidence"]].sample(20, random_state=42)
for _, row in sample.iterrows():
    print(f"  [{row['classification']:6s} / {row['classification_confidence']:6s}] {row['Resolution'][:90]}")
