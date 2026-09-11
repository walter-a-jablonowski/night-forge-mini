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
