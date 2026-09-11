"""The seam between the loop and whatever actually answers a prompt.

Everything that knows HOW a model is reached lives behind this interface: an
OpenAI-compatible HTTP endpoint today, an agent CLI on the user's own subscription next
(see tasks/backlog/claude-code-backend.md). A pack calls `complete_json` / `run_tools` and
never learns which it has.

Two backends already existed before this seam did — the real client and `--fake-llm` — but
the second was dispatched by an `if model.fake:` inside every pack's `analyze`, so each new
kind meant another branch in each pack. That is what this replaces.

Registration follows the tools house style: explicit wiring in `__init__.py`, no import-time
magic in the modules themselves.
"""
from __future__ import annotations

import json
import re
from typing import Any, Protocol, runtime_checkable


class LLMError(RuntimeError):
    """Anything that went wrong reaching or parsing the model. Shared by all backends so
    callers can catch one type regardless of which one is configured."""


@runtime_checkable
class Backend(Protocol):
    """One way of answering a prompt.

    `complete_json` is the one-shot call; `run_tools` is the agentic one — note that a
    backend may run the tool loop ITSELF (an agent CLI does) rather than handing single
    steps back, so implementations must not assume the caller drives it.
    """

    # True when this backend reaches no model at all (`--fake-llm`). Declared here on
    # purpose: a caller that must stay deterministic offline — a pack's analyze, an
    # LLM-judged metric — has to know BEFORE it asks, and should not have to read an
    # implementation's attributes to find out. Branching on this is correct; what the
    # offline answer looks like is domain knowledge and stays in the pack.
    fake: bool

    def complete_json(self, system: str, user: str,
                      schema: dict | None = None) -> dict[str, Any]:
        """One completion that must yield a JSON object."""
        ...

    def run_tools(self, system: str, user: str, tools: list,
                  schema: dict | None = None, **kwargs) -> dict[str, Any]:
        """Let the model read with READ-ONLY tools, then return the same JSON object."""
        ...

    def take_tool_trace(self) -> list[dict]:
        """Spans of the tool calls made since the last take, for the Engine to log."""
        ...

    def label(self) -> str:
        """What answered, for the run record (e.g. `openrouter:z-ai/glm-5.2`)."""
        ...


_backends: dict[str, Any] = {}


def register(name: str, build) -> None:
    """`build(cfg) -> Backend`. A factory rather than an instance: a backend needs the
    deploy's config (endpoint, key, binary path) and must not be constructed at import."""
    _backends[name] = build


def get(name: str):
    return _backends.get(name)


def names() -> list[str]:
    return sorted(_backends)


def _extract_json(text: str) -> dict[str, Any]:
    """Tolerant JSON parse — models sometimes wrap JSON in prose or code fences.

    Every parse failure must leave as `LLMError`, because that is what the retry in
    `_request_json` catches. `ValueError`, not `JSONDecodeError`, is the net to use: a
    judge once answered with a 64714-digit number, where `json.loads` raises a bare
    ValueError from int() — which escaped both the fallback below and the retry, and
    surfaced as a crashed metric instead of a second attempt."""
    text = text.strip()
    try:
        return _as_object(json.loads(text))
    except ValueError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return _as_object(json.loads(m.group(0)))
        except ValueError as e:
            raise LLMError(f"model did not return valid JSON: {e}\n---\n{text[:500]}")
    raise LLMError(f"no JSON found in model output:\n{text[:500]}")


def _as_object(parsed: Any) -> dict[str, Any]:
    """Valid JSON that is not an object is still the wrong answer here — every caller
    expects a dict, so treat it like any other parse failure (retryable)."""
    if not isinstance(parsed, dict):
        raise ValueError(f"expected a JSON object, got {type(parsed).__name__}")
    return parsed
