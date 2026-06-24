"""FROZEN resolution taxonomy for KDS.

This module is the single semantic contract for what counts as a policy, value,
or fact motion. Every generator that conditions on motion type imports these
definitions and gold examples. Changing these definitions is a deliberate act —
do not edit casually, because downstream prompts and (eventually) fine-tuning
labels depend on this exact boundary.

KEY RULING (documented, intentional): comparative phrasing is split by *what is
being compared*, matching the existing rule-based classifier:

  * "X is BETTER THAN Y" / "X does MORE HARM THAN GOOD"  -> FACT
        (an empirical/descriptive claim about outcomes in the world)
  * "X OUTWEIGHS Y" / "X is PREFERABLE TO Y" / "values X OVER Y" -> VALUE
        (a normative/priority claim about what we *ought* to weigh more)

This boundary is accidental-by-regex but adopted on purpose so the data and the
generators agree. Revisit only with a corpus re-label.
"""

from __future__ import annotations

from enum import Enum


class MotionType(str, Enum):
    POLICY = "policy"
    VALUE = "value"
    FACT = "fact"


# ── canonical definitions ────────────────────────────────────────────────────
DEFINITIONS: dict[MotionType, str] = {
    MotionType.POLICY: (
        "A POLICY motion prescribes an actor taking an action. It typically "
        "contains 'should', 'would', 'ought to <act>', or a parliamentary "
        "directive (This House Would / Supports / Opposes). The clash is over "
        "whether the proposed action should be taken — its plan, advantages, "
        "and disadvantages."
    ),
    MotionType.VALUE: (
        "A VALUE motion asserts a normative or comparative-priority judgement: "
        "what is just/unjust, moral/immoral, legitimate, a right, or what we "
        "OUGHT to prioritize/prefer/value OVER something else (outweighs, "
        "preferable to, more important than). The clash is over a criterion of "
        "evaluation, not an empirical outcome."
    ),
    MotionType.FACT: (
        "A FACT motion makes an empirical or descriptive claim about the world "
        "that is true or false in principle: X has improved/worsened Y, X is "
        "effective, X is the primary cause of Y, or X does MORE HARM/GOOD THAN "
        "Y / is BETTER THAN Y. The clash is over evidence and measurable "
        "outcomes."
    ),
}


# ── gold examples (drawn from the real corpus, high confidence) ───────────────
EXAMPLES: dict[MotionType, list[str]] = {
    MotionType.POLICY: [
        "Lobbying should be banned in US politics.",
        "The US Federal Government should implement more checks for the executive branch.",
        "America's European allies should reduce their security cooperation with the US.",
        "NATO should remove the United States from its membership.",
        "This house believes that the media should show the full horror of war.",
        "Mexico should lift its ban on planting genetically modified corn.",
    ],
    MotionType.VALUE: [
        "This house values hard work over creativity.",
        "Law Enforcement's use of facial recognition technology is just.",
        "Courts ought to include the victims' forgiveness as a mitigating factor in sentencing.",
        "This House Believes That the existence of billionaires is immoral.",
        "Developing economies ought to prioritize economic growth over controlling government debt.",
        "It is unjust to receive income that comes not from working but from owning.",
    ],
    MotionType.FACT: [
        "Online education has improved education.",
        "Public protests are effective.",
        "California product label laws are doing more good than harm.",
        "China's rapid expansion of the Electric Vehicles industry has done more harm than good.",
        "Strong dictatorship is better than weak democracy.",
        "This House believes the medicalization of weight loss does more good than harm.",
    ],
}


def definition(motion_type: MotionType | str) -> str:
    return DEFINITIONS[MotionType(motion_type)]


def examples(motion_type: MotionType | str, n: int | None = None) -> list[str]:
    ex = EXAMPLES[MotionType(motion_type)]
    return ex[:n] if n else list(ex)


def taxonomy_prompt_block() -> str:
    """Render the full taxonomy as a system-prompt-ready block."""
    lines = ["MOTION TAXONOMY (authoritative):"]
    for mt in MotionType:
        lines.append(f"\n{mt.value.upper()}: {DEFINITIONS[mt]}")
        lines.append("Examples:")
        for ex in EXAMPLES[mt]:
            lines.append(f"  - {ex}")
    lines.append(
        "\nComparative ruling: 'better than' / 'more harm than good' => FACT; "
        "'outweighs' / 'preferable to' / 'values X over Y' => VALUE."
    )
    return "\n".join(lines)
