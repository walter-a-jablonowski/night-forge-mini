"""One thin client wrapper around the model call (idea_2 seam).

Provider-agnostic: OpenRouter (default), Gemini, and Ollama all speak the
OpenAI-compatible chat API, so a single client switches by base_url + key + model.
This is also where a Langfuse/OTel callback would later be added — one call site.

`--fake-llm` skips the network entirely and returns a deterministic proposal, so the
whole loop runs and is testable with no key and no token spend.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any


class LLMError(RuntimeError):
    pass


class ModelWrapper:
    def __init__(self, provider: dict[str, Any], fake: bool = False):
        self.provider = provider
        self.fake = fake
        self._client = None

    # The single model call site.
    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        if self.fake:
            raise LLMError("complete_json called in fake mode; analyzer should branch earlier")
        client = self._ensure_client()
        resp = client.chat.completions.create(
            model=self.provider["model"],
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
        )
        text = resp.choices[0].message.content or ""
        return _extract_json(text)

    def label(self) -> str:
        return f'{self.provider["name"]}:{self.provider["model"]}'

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover
            raise LLMError("openai package not installed; `pip install -r requirements.txt` or use --fake-llm") from e
        key = os.environ.get(self.provider.get("api_key_env", ""), "") or "no-key"
        self._client = OpenAI(base_url=self.provider["base_url"], api_key=key)
        return self._client


def _extract_json(text: str) -> dict[str, Any]:
    """Tolerant JSON parse — models sometimes wrap JSON in prose or code fences."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise LLMError(f"model did not return valid JSON: {e}\n---\n{text[:500]}")
    raise LLMError(f"no JSON found in model output:\n{text[:500]}")
