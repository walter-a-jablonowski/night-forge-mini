"""The backends. Importing this package wires the built-in ones into the registry.

`http` is every OpenAI-compatible provider (config `providers{}` + `provider`); the fake
one and an agent CLI are siblings, added here as they land. `build` assembles a deploy's
backend from them, routing one-shot calls separately (`one_shot`, see routed.py).
"""
from __future__ import annotations

from .base import Backend, LLMError, get, names, register
from .claude_code import ClaudeCodeBackend
from .fake import FakeBackend
from .http import HttpBackend
from .routed import RoutedBackend, build  # where each kind of call goes (one_shot)

# explicit wiring (no import-time magic inside the backend modules) — the whole built-in
# set is visible here in one place. A factory, not an instance: a backend is built from
# the deploy's config.
register("http", lambda cfg: HttpBackend(cfg.provider()))
register("fake", lambda cfg: FakeBackend())
register("claudeCode", lambda cfg: ClaudeCodeBackend(cfg))

__all__ = ["Backend", "ClaudeCodeBackend", "FakeBackend", "HttpBackend", "LLMError",
           "RoutedBackend", "build", "get", "names", "register"]
