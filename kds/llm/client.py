"""Provider-agnostic LLM client.

Wraps the OpenAI-compatible chat endpoints that both Groq and Together expose,
so swapping provider/model is a config change, never a code change. Includes
retry with backoff, optional JSON mode, and automatic call logging.

The ``openai`` package is imported lazily so the rest of KDS (corpus, schemas,
taxonomy) works with zero extra dependencies. A ``dry_run`` mode builds and logs
the request WITHOUT any network call, which is how tests and credential-less
environments exercise the client.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from .. import config
from . import logging as gen_logging


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, settings: Optional[config.Settings] = None):
        self.settings = settings or config.get_settings()
        self._client = None  # lazily constructed

    # ── internal ──────────────────────────────────────────────────────────────
    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not self.settings.has_credentials():
            raise LLMError(
                f"No API key set ({self.settings.provider_cfg['api_key_env']}). "
                f"Add it to the environment or secret.txt, or use dry_run=True."
            )
        try:
            from openai import OpenAI  # lazy import
        except ImportError as e:  # pragma: no cover
            raise LLMError(
                "The 'openai' package is required for live calls. "
                "Install it: pip install openai"
            ) from e
        self._client = OpenAI(
            base_url=self.settings.provider_cfg["base_url"],
            api_key=self.settings.api_key,
            timeout=self.settings.request_timeout,
        )
        return self._client

    def build_messages(self, system: str, user: str, fewshots=None) -> list[dict]:
        messages: list[dict] = [{"role": "system", "content": system}]
        for shot in fewshots or []:
            # fewshots may be (user, assistant) tuples or pre-built dicts
            if isinstance(shot, dict):
                messages.append(shot)
            else:
                u, a = shot
                messages.append({"role": "user", "content": u})
                messages.append({"role": "assistant", "content": a})
        messages.append({"role": "user", "content": user})
        return messages

    # ── public ────────────────────────────────────────────────────────────────
    def chat(
        self,
        system: str,
        user: str,
        *,
        generator: str = "ad_hoc",
        type_tag: Optional[str] = None,
        fewshots: Optional[list[Any]] = None,
        json_mode: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        log: bool = True,
        dry_run: bool = False,
    ) -> str:
        """Run a chat completion and return the assistant text.

        ``dry_run=True`` skips the network call, returns a placeholder, and still
        logs a record (with params marked dry_run) so the logging path is testable
        offline.
        """
        messages = self.build_messages(system, user, fewshots)
        params = {
            "model": self.settings.resolved_model,
            "provider": self.settings.provider,
            "temperature": temperature
            if temperature is not None
            else self.settings.temperature,
            "max_tokens": max_tokens or self.settings.max_tokens,
            "json_mode": json_mode,
        }

        if dry_run:
            output = "[DRY_RUN] no network call performed"
            params = {**params, "dry_run": True}
        else:
            output = self._call_with_retry(messages, params, json_mode)

        if log:
            gen_logging.log_generation(
                generator=generator,
                system=system,
                user=user,
                output=output,
                type_tag=type_tag,
                fewshots=fewshots,
                params=params,
            )
        return output

    def _call_with_retry(self, messages, params, json_mode) -> str:
        client = self._ensure_client()
        kwargs = {
            "model": params["model"],
            "messages": messages,
            "temperature": params["temperature"],
            "max_tokens": params["max_tokens"],
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        last_err: Exception | None = None
        for attempt in range(self.settings.max_retries):
            try:
                resp = client.chat.completions.create(**kwargs)
                return resp.choices[0].message.content or ""
            except Exception as e:  # broad: providers raise varied error types
                last_err = e
                status = getattr(e, "status_code", None)
                msg = str(e)
                # 413 / "request too large": retrying the same payload won't help.
                if status == 413 or "Request too large" in msg:
                    raise LLMError(
                        f"Payload too large for the model's per-request limit: {e}"
                    ) from e
                # 429 / TPM rate limit: wait out the window (longer backoff).
                if status == 429 or "rate_limit" in msg.lower():
                    time.sleep(min(20 * (attempt + 1), 60))
                else:
                    time.sleep(min(2**attempt, 30))
        raise LLMError(f"LLM call failed after retries: {last_err}")


def chat_json(client: LLMClient, system: str, user: str, **kw) -> dict:
    """Convenience: call in JSON mode and parse, with one repair retry."""
    raw = client.chat(system, user, json_mode=True, **kw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        repair = client.chat(
            system,
            user + "\n\nYour previous reply was not valid JSON. Return ONLY valid JSON.",
            json_mode=True,
            **kw,
        )
        return json.loads(repair)
