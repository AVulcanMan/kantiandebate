"""Central configuration for KDS.

All tunables live here so call sites never hardcode a provider, model, or path.
Secrets are read from the environment. As a convenience for local dev, a
``secret.txt`` file (KEY=VALUE per line, untracked) is loaded into the
environment on import if present — but it is NEVER printed or committed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ── paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
FOOTAGE_DIR = DATA_DIR / "footage"

RAW_CSV = DATA_DIR / "parliresolutions.csv"
CLASSIFIED_CSV = DATA_DIR / "parliresolutions_classified.csv"
CORPUS_DB = DATA_DIR / "corpus.sqlite"
GENERATIONS_LOG = LOGS_DIR / "generations.jsonl"
CONFIG_TOML = ROOT / "config.toml"


def load_toml() -> dict:
    """Read the editable config.toml (returns {} if absent or unparseable)."""
    if not CONFIG_TOML.exists():
        return {}
    try:
        import tomllib

        return tomllib.loads(CONFIG_TOML.read_text(encoding="utf-8"))
    except Exception:
        return {}


_TOML = load_toml()


def _load_secret_file() -> None:
    """Load KEY=VALUE pairs from secret.txt into os.environ (no-op if absent).

    Never logs or prints values. Existing env vars take precedence.
    """
    secret = ROOT / "secret.txt"
    if not secret.exists():
        return
    # Bare-token prefixes -> which env var they map to.
    BARE_PREFIXES = {
        "gsk_": "GROQ_API_KEY",
        "sk-": "OPENAI_API_KEY",
    }
    try:
        for line in secret.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
                continue
            # Bare token on its own line: infer the env var from its prefix.
            for prefix, env_var in BARE_PREFIXES.items():
                if line.startswith(prefix):
                    os.environ.setdefault(env_var, line)
                    break
            else:
                # Unknown bare token: assume it's the default provider's key.
                default_env = PROVIDERS.get(
                    os.environ.get("KDS_PROVIDER", "groq"), {}
                ).get("api_key_env")
                if default_env:
                    os.environ.setdefault(default_env, line)
    except Exception:
        # A malformed secret file must never crash imports.
        pass


# ── LLM provider config ──────────────────────────────────────────────────────
# Both Groq and Together expose OpenAI-compatible chat endpoints, so a single
# client works for both — only base_url, key env var, and model name change.
PROVIDERS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "api_key_env": "TOGETHER_API_KEY",
        "default_model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    },
}

_load_secret_file()  # after PROVIDERS so the bare-token fallback can resolve it


def _layered(env: str, toml_section: str, toml_key: str, default):
    """Precedence: environment variable > config.toml > hardcoded default."""
    if env in os.environ:
        return os.environ[env]
    return _TOML.get(toml_section, {}).get(toml_key, default)


@dataclass
class Settings:
    # default_factory so env/toml are resolved at instantiation, not import time.
    provider: str = field(
        default_factory=lambda: str(_layered("KDS_PROVIDER", "llm", "provider", "groq"))
    )
    model: str | None = field(
        default_factory=lambda: os.environ.get("KDS_MODEL") or _TOML.get("llm", {}).get("model")
    )
    temperature: float = field(
        default_factory=lambda: float(_layered("KDS_TEMPERATURE", "llm", "temperature", 0.7))
    )
    max_tokens: int = field(
        default_factory=lambda: int(_layered("KDS_MAX_TOKENS", "llm", "max_tokens", 1024))
    )
    request_timeout: float = field(
        default_factory=lambda: float(os.environ.get("KDS_TIMEOUT", "60"))
    )
    max_retries: int = field(default_factory=lambda: int(os.environ.get("KDS_MAX_RETRIES", "4")))

    # ASR backend: "groq_whisper" (hosted fallback) or "collaborator" (GPU fleet).
    asr_backend: str = field(
        default_factory=lambda: str(_layered("KDS_ASR_BACKEND", "asr", "backend", "groq_whisper"))
    )

    extra: dict = field(default_factory=dict)

    @property
    def provider_cfg(self) -> dict:
        if self.provider not in PROVIDERS:
            raise ValueError(
                f"Unknown provider {self.provider!r}; choose from {list(PROVIDERS)}"
            )
        return PROVIDERS[self.provider]

    @property
    def resolved_model(self) -> str:
        return self.model or self.provider_cfg["default_model"]

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.provider_cfg["api_key_env"])

    def has_credentials(self) -> bool:
        return bool(self.api_key)


def get_settings() -> Settings:
    return Settings()


def motion_config() -> dict:
    """Editable motion-generation tunables from config.toml (with defaults)."""
    m = _TOML.get("motion", {})
    return {
        "n_fewshots": int(m.get("n_fewshots", 4)),
        "fewshot_min_confidence": str(m.get("fewshot_min_confidence", "high")),
        "news_count": int(m.get("news_count", 8)),
    }


def ensure_dirs() -> None:
    for d in (DATA_DIR, LOGS_DIR, TRANSCRIPTS_DIR, FOOTAGE_DIR):
        d.mkdir(parents=True, exist_ok=True)
