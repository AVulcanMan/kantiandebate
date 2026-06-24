# KDS evaluation rubrics

The `eval` harness scores generator output so you can tell whether a prompt edit
helped. Run `python cli.py eval motion` after editing a prompt and compare scores.

## Motion generator

Each generated motion is scored on three axes:

| Metric | How | Source |
|---|---|---|
| **type_accuracy** | Does the rule classifier agree the motion is the requested type? | deterministic (`kds.corpus.classify`) — free, fast |
| **specificity** | 0–5: concrete actor + mechanism (esp. policy) vs vague | LLM judge (`prompts/motion_judge.md`) |
| **debatability** | 0–5: can both sides realistically win? | LLM judge |

Aggregate score per run = mean over all motions of:
`type_accuracy (0/1) * 4 + specificity/5 * 3 + debatability/5 * 3` → 0–10 scale.

### Targets
- type_accuracy ≥ 0.85
- specificity ≥ 3.5 (policy especially — this is what the "be more specific" tuning targets)
- debatability ≥ 4.0

## Cases
Edit `eval/cases/motion.jsonl` to add/remove test cases (one JSON object per line:
`{"type": "...", "theme": "...", "n": N}`). More cases = more stable scores, more API calls.
