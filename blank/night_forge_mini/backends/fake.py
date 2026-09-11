"""The offline backend — what `--fake-llm` selects.

It reaches no model and answers no prompt: a caller that must work offline branches on
`fake` BEFORE asking, and produces its own deterministic result. That is deliberate. What
a plausible proposal looks like is domain knowledge (the KB pack invents entries, the
website pack invents pages from the site it can see), so it belongs in the pack, not in a
domain-agnostic backend that has only prompt strings to work from.

This backend's job is therefore to be honest about being fake and to fail loudly if
something asks it for a completion anyway — a silent stub would turn a missed branch into
an invented answer, which is the failure mode this project cares most about avoiding.
"""
from __future__ import annotations

from typing import Any

from .base import LLMError


class FakeBackend:
    """`base.Backend` that never calls anything. Deterministic by construction."""

    fake = True

    def __init__(self, provider: dict[str, Any] | None = None):
        self.provider = provider or {}

    def complete_json(self, system: str, user: str,
                      schema: dict | None = None) -> dict[str, Any]:
        raise LLMError("complete_json called on the fake backend; the caller should have "
                       "branched on `fake` and produced a deterministic result itself")

    def run_tools(self, system: str, user: str, tools: list,
                  schema: dict | None = None, **kwargs) -> dict[str, Any]:
        raise LLMError("run_tools called on the fake backend; the caller should have "
                       "branched on `fake` and produced a deterministic result itself")

    def take_tool_trace(self) -> list[dict]:
        return []

    def label(self) -> str:
        return "fake-llm"
