"""Tool registry — the core's pluggable toolbox (see tasks/backlog/tool-registry.md).

A *tool* is a domain-agnostic capability a pack's connector / action / analyze can call
(fetch a URL, strip HTML, ...). The blank core ships a few stdlib-only built-ins; a pack
registers its own (keyed / heavy) tools inside `build_pack(cfg)`. Tools sit BELOW the
`Connector` seam — they are helpers a `fetch()` / action calls, not a replacement for it.

Registration is explicit (no decorator, no import-time magic): `tools/__init__.py` wires the
built-ins, and a pack calls `registry.register(...)` in `build_pack(cfg)` so a tool can close
over config and credentials. Secrets come from `.env` (a tool names the env-var via
`requires`, never the secret); non-secret params come from `config.json`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Tool:
    """One reusable capability. `run(**kwargs)` performs it. `requires` lists the env-var
    names the tool needs (e.g. an API key); the default `available()` is True only when all
    of them are set, so a keyed tool disables gracefully when its key is missing. For a
    non-env precondition (e.g. a binary on PATH), pass `available_check`."""
    name: str
    description: str
    run: Callable[..., Any]
    requires: list[str] = field(default_factory=list)
    available_check: Callable[[], bool] | None = None

    def available(self) -> bool:
        if self.available_check is not None:
            return self.available_check()
        return all(os.environ.get(k) for k in self.requires)


class Registry:
    """A tiny name -> Tool map. One module-level singleton `registry` holds the built-ins;
    `Registry` stays instantiable so tests can use a fresh, isolated registry."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"tool '{tool.name}' already registered")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> list[Tool]:
        return list(self._tools.values())


# The default toolbox. tools/__init__.py registers the built-ins into it on import.
registry = Registry()
