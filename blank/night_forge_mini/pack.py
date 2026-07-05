"""The domain-pack seam — the only thing a domain must satisfy to plug into the core.

A pack provides exactly the "four things" (see tasks/resources/v1-blank-sys-and-domain-pack.md):
  1. a connector  — `fetch(seen_ids) -> artifacts`
  2. goal         — what "good" means for the domain
  3. analysis     — `(model, *, goal, snippets, history) -> {finding, metric, actions}`
                    `history` = {findings, metrics, rejections, failures} from past runs
  4. actions      — name -> Action, each carrying honest `risk_level` + `reversible` + `run`

The core sanitizes whatever `analyze` returns (`sanitize_actions`): malformed model
output can never crash the loop or weaken the gate — a pack does not have to (and
cannot be trusted to) sanitize it itself.

Registration is deliberately trivial (one pack per deployment, no registry): a domain
is a folder providing a `domain_pack` package that exposes `build_pack(cfg) -> Pack`.
The core does `import domain_pack; pack = domain_pack.build_pack(cfg)`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .records import new_id


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
    # (model, *, goal, snippets, history) -> {finding, metric, actions, model}
    analyze: Callable[..., dict[str, Any]]


def sanitize_actions( raw: Any, actions: dict[str, Action] ) -> tuple[list[dict], list[Any]]:
    """The sanitizing boundary for model output — enforced by the core, not the pack.

    Returns (sanitized, dropped). Kept actions are copies with `action_id`/`target`/
    `rationale`/`payload` guaranteed present, and `risk_level` + `reversible` ALWAYS
    stamped from the pack's Action — the model cannot understate risk or claim
    reversibility. Anything malformed (non-dict, unknown name) lands in `dropped` so
    it is logged, never silently lost."""
    ok: list[dict] = []
    dropped: list[Any] = []
    if not isinstance(raw, list):
        return ok, ([] if raw is None else [raw])
    for item in raw:
        act = actions.get(item.get("name")) if isinstance(item, dict) else None
        if act is None:
            dropped.append(item)
            continue
        a = dict(item)
        a.setdefault("action_id", new_id("act"))
        a["target"] = str(a.get("target") or "")
        a.setdefault("rationale", "")
        a["payload"] = a["payload"] if isinstance(a.get("payload"), dict) else {}
        a["risk_level"] = act.risk_level
        a["reversible"] = act.reversible
        ok.append(a)
    return ok, dropped
