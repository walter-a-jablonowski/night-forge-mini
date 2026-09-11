"""The backends. Importing this package wires the built-in ones into the registry.

`http` is every OpenAI-compatible provider (config `providers{}` + `provider`); the fake
one and an agent CLI are siblings, added here as they land. See
tasks/backlog/claude-code-backend.md.
"""
from __future__ import annotations

from .base import Backend, LLMError, get, names, register
from .http import HttpBackend

# explicit wiring (no import-time magic inside the backend modules) — the whole built-in
# set is visible here in one place. A factory, not an instance: a backend is built from
# the deploy's config.
register("http", lambda cfg, **kw: HttpBackend(cfg.provider(), **kw))

__all__ = ["Backend", "HttpBackend", "LLMError", "get", "names", "register"]
