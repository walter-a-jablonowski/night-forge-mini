"""Where each kind of model call goes — the agent pass and the one-shot call, routed apart.

A deploy makes two kinds of call (see base.Backend):
  run_tools      the agentic analyze pass
  complete_json  one-shot: an LLM-judged metric, or analyze with analyze_tool_steps 0

`backend` picks where the first goes. `one_shot` picks the second:

    "one_shot": "gemini"       a key of `providers` -> that HTTP provider
    "one_shot": "claudeCode"   the Claude Code CLI, no api key (`claudeCode.oneShotModel`)
    absent                     `provider` when one is configured, else the backend itself

The one-shot role used to be hard-wired: the Claude Code backend always sent it to the HTTP
provider, on the premise that the CLI could not be constrained to JSON. It can
(`--json-schema`, verified 2026-10-11), so a subscription-only deploy needs no provider key
at all, and an HTTP deploy can judge with a different vendor than it analyzes with.
"""
from __future__ import annotations

from typing import Any

from .base import add_usage, get, names
from .claude_code import ClaudeCodeBackend
from .http import HttpBackend


class RoutedBackend:
    """`base.Backend` over two backends, one per kind of call."""

    fake = False    # a fake deploy is never routed: see `build`

    def __init__(self, agent, one_shot):
        self.agent = agent
        self.one_shot = one_shot

    def complete_json(self, system: str, user: str,
                      schema: dict | None = None) -> dict[str, Any]:
        return self.one_shot.complete_json(system, user, schema)

    def run_tools(self, system: str, user: str, tools: list,
                  schema: dict | None = None, **bounds) -> dict[str, Any]:
        return self.agent.run_tools(system, user, tools, schema, **bounds)

    def take_tool_trace(self) -> list[dict]:
        # a one-shot call can leave spans too (an HTTP retry), and a pass makes both kinds
        return self.agent.take_tool_trace() + self.one_shot.take_tool_trace()

    def take_usage(self) -> dict[str, float]:
        total: dict[str, float] = {}
        for part in (self.agent.take_usage(), self.one_shot.take_usage()):
            add_usage(total, **part)
        return total

    def label(self) -> str:
        return f"{self.agent.label()} + one-shot {self.one_shot.label()}"


def build(cfg, name: str):
    """The deploy's backend: the one named `name`, routed for one-shot calls if they go
    elsewhere. Same route and model -> the agent backend itself, unwrapped."""
    make = get(name)
    if make is None:
        raise ValueError(f"config: unknown backend {name!r} (known: {', '.join(names())})")
    agent = make(cfg)
    if agent.fake:
        return agent    # offline: nothing may reach a model, whatever the routing says
    one_shot = _one_shot(cfg, name)
    return agent if one_shot.label() == agent.label() else RoutedBackend(agent, one_shot)


def _one_shot(cfg, name: str):
    route = cfg.get("one_shot") or cfg.get("provider") or name
    providers = cfg.get("providers") or {}
    if route in providers:
        return HttpBackend(cfg.provider(route))
    if route == "claudeCode":
        return ClaudeCodeBackend(cfg, model=(cfg.get("claudeCode") or {}).get("oneShotModel"))
    raise ValueError(f"config: one_shot {route!r} must be a key of providers "
                     f"({', '.join(providers) or 'none configured'}) or claudeCode")
