"""The backends. Importing this package wires the built-in ones into the registry.

`http` is every OpenAI-compatible provider (config `providers{}` + `provider`); the fake
one and an agent CLI are siblings, added here as they land. See
tasks/backlog/claude-code-backend.md.
"""
from __future__ import annotations

from .base import Backend, LLMError, get, names, register
from .claude_code import ClaudeCodeBackend
from .fake import FakeBackend
from .http import HttpBackend

# explicit wiring (no import-time magic inside the backend modules) — the whole built-in
# set is visible here in one place. A factory, not an instance: a backend is built from
# the deploy's config.
register("http", lambda cfg: HttpBackend(cfg.provider()))
register("fake", lambda cfg: FakeBackend(cfg.provider()))
# the agent CLI: agentic passes go to it, one-shot calls (a judged metric) go to
# the configured http provider instead — see claude_code.py
register("claudeCode",
         lambda cfg: ClaudeCodeBackend(cfg, one_shot=HttpBackend(cfg.provider())))

__all__ = ["Backend", "ClaudeCodeBackend", "FakeBackend", "HttpBackend", "LLMError",
           "get", "names", "register"]
