# Transcript JSON Contract

Transcripts consumed by the KDS pipeline are stored as JSON files containing a list of **Segment** objects. This schema is the canonical contract between transcript producers (collaborator tooling or ASR fallback) and the KDS pipeline.

## Top-level structure

```json
{
  "source": "<string — YouTube URL, filename, or identifier>",
  "metadata": {
    "title": "<string — optional>",
    "channel": "<string — optional>",
    "duration_seconds": "<float — optional>"
  },
  "segments": [ <Segment>, ... ]
}
```

The `segments` array is required. `source` and `metadata` are optional but strongly recommended for traceability.

## Segment object

| Field | Type | Required | Description |
|---|---|---|---|
| `text` | string | YES | Transcript text for this segment. May be a sentence or a speaker turn. |
| `start` | float | YES | Start timestamp in seconds (relative to the beginning of the audio). |
| `end` | float | YES | End timestamp in seconds. Must be >= `start`. |
| `speaker` | string | NO | Speaker label (e.g. `"GOV1"`, `"OPP2"`, `"Speaker A"`). Null or absent if diarization is unavailable. |
| `confidence` | float | NO | ASR confidence score in [0.0, 1.0]. Null or absent if the backend does not emit per-segment scores. |

### Minimal valid segment

```json
{"text": "Climate change is the defining issue of our generation.", "start": 0.0, "end": 4.2}
```

### Full segment

```json
{
  "text": "The government has a responsibility to ensure access to healthcare.",
  "start": 12.4,
  "end": 17.1,
  "speaker": "GOV1",
  "confidence": 0.94
}
```

## Constraints

- `text` must be a non-empty string.
- `start` and `end` must be non-negative floats with `end >= start`.
- `confidence`, when present, must be in [0.0, 1.0].
- `speaker` is a free-form string; downstream code that depends on speaker labels should tolerate absent or null values gracefully.
- Segments are expected to be in chronological order (ascending `start`), but consumers should not require strictly non-overlapping intervals — overlap can arise from multi-speaker ASR.

## ASR backend decision (Phase 0)

For development, the fallback backend is **Groq Whisper** (hosted ASR). The collaborator GPU fleet can be swapped in by changing `ASR_BACKEND` in `kds/config.py`. Both backends must produce output conforming to this schema via `kds/pipeline/transcript_io.py`.

## Pydantic model

The authoritative Python representation is `kds.schemas.Segment`. Load and validate a transcript file with:

```python
from kds.schemas import Segment
import json

with open("data/transcripts/sample_round.json") as f:
    data = json.load(f)
segments = [Segment(**s) for s in data["segments"]]
```
