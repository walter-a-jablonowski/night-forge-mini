"""The domain-pack seam — the only thing a domain must satisfy to plug into the core.

A pack provides exactly the "four things" (see tasks/resources/v1-blank-sys-and-domain-pack.md):
  1. a connector  — `fetch(seen_ids) -> artifacts`
  2. goal         — what "good" means for the domain
  3. analysis     — `(model, *, goal, snippets, recent_findings) -> {finding, metric, actions}`
  4. actions      — name -> Action, each carrying honest `risk_level` + `reversible` + `run`

Registration is deliberately trivial (one pack per deployment, no registry): a domain
is a folder providing a `domain_pack` package that exposes `build_pack(cfg) -> Pack`.
The core does `import domain_pack; pack = domain_pack.build_pack(cfg)`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


class Connector(Protocol):
    name: str

    def fetch(self, seen_ids: set[str]) -> list[dict]:
        """Return new artifacts not in seen_ids. Each: {id, text, source}."""
        ...


@dataclass
class Action:
    """One output the agent may propose. The gate reads `reversible` (hard floor) and
    `risk_level`; `run(target, payload) -> {status, detail}` performs the side-effect."""
    name: str
    risk_level: str
    reversible: bool
    run: Callable[[str, dict], dict]


@dataclass
class Pack:
    domain: str
    goal: str
    connector: Connector
    actions: dict[str, Action]
    # (model, *, goal, snippets, recent_findings) -> {finding, metric, actions, model}
    analyze: Callable[..., dict[str, Any]]
