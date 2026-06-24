"""Base machinery for LLM generators.

Every generator builds a system + user prompt, calls the provider-agnostic
client in JSON mode, parses, and validates against a pydantic model (with one
repair retry). All calls are logged via the client for the training corpus.
"""

from __future__ import annotations

import json
from typing import Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from ..llm.client import LLMClient

T = TypeVar("T", bound=BaseModel)


class Generator:
    name: str = "generator"

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient()

    def _generate_json(
        self,
        system: str,
        user: str,
        *,
        type_tag: Optional[str] = None,
        fewshots: Optional[list] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        dry_run: bool = False,
    ) -> dict:
        """Call the model in JSON mode and parse to a dict, with one repair retry."""
        raw = self.client.chat(
            system,
            user,
            generator=self.name,
            type_tag=type_tag,
            fewshots=fewshots,
            json_mode=True,
            temperature=temperature,
            max_tokens=max_tokens,
            dry_run=dry_run,
        )
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            repair = self.client.chat(
                system,
                user + "\n\nYour previous reply was not valid JSON. Reply with ONLY valid JSON.",
                generator=self.name,
                type_tag=type_tag,
                json_mode=True,
                temperature=temperature,
                max_tokens=max_tokens,
                dry_run=dry_run,
            )
            return json.loads(repair)

    def _validate(self, model: Type[T], data: dict) -> T:
        try:
            return model.model_validate(data)
        except ValidationError as e:
            raise ValueError(f"{self.name}: output failed schema validation: {e}") from e
