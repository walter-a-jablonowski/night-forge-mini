"""Metric targets — the loop's answer to "are we done?" (tasks/backlog/run-when-metric-below-target.md).

The metric is measured every pass. Without a target it is compared to nothing, so a loop
with no new input could neither keep working toward its goal nor say it had reached it.
One comparison answers both:

    "metric_targets":   {"goal_coverage": 8, "broken_links": {"max": 0}}   number = at least
    "convergence_runs": 3

check(runs) -> Verdict.state
  none       no targets configured — the loop behaves exactly as before
  met        every target is met on its last measured value — stop: "goal reached"
  blind      a target was not measured in any of the last N runs — stop: "cannot measure"
  converged  not met, and no targeted metric beat its best value over the last N runs that
             had a chance to move it — stop: "stopped improving"
  unmet      a pass may run without new input, for this reason

A missing measurement is NOT a flat one. The first version treated it as such and stopped a
live deploy with "stopped improving" while the site grew from 3 to 5 pages — the judge had
hit its daily quota in two of the three passes. So:
  - targets read the LAST MEASURED value, so one failed judge call does not freeze the loop,
  - convergence needs real measurements before AND inside the N-run window, and compares
    best values, so one noisy low score does not stop the loop,
  - and a metric that cannot be measured at all stops the loop after N blind passes rather
    than letting it run on a goal it cannot see.

`met` is checked BEFORE `converged`: a finished artifact plateaus at its ceiling, and it
must stop with "goal reached", not "stopped improving" — the two call for opposite
responses from the operator (accept, versus change the goal, the tools or the model).

The value used is the LAST RECORDED one, i.e. measured at the start of the previous pass,
before its actions ran. Deliberately one run stale: measuring fresh would mean an LLM call
(a judged metric) just to decide whether to think. The cost is at most one extra pass.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_PATIENCE = 3   # two passes can legitimately set up a third without moving a number


@dataclass(frozen=True)
class Target:
    key: str
    bound: float
    at_least: bool          # False = "at most" (fewer is better, e.g. broken_links)

    def met(self, value: Any) -> bool:
        if not _number(value):
            return False    # not measured is not met — the goal cannot be claimed blind
        return value >= self.bound if self.at_least else value <= self.bound

    def best(self, values: list[float]) -> float:
        return max(values) if self.at_least else min(values)

    def gain(self, before: Any, after: Any) -> float:
        """Movement TOWARD the bound; beyond it counts for nothing, so a metric that keeps
        growing after it is met does not keep a stalled goal looking alive."""
        if not (_number(before) and _number(after)):
            return 0.0
        if self.at_least:
            return min(after, self.bound) - min(before, self.bound)
        return max(before, self.bound) - max(after, self.bound)

    def show(self, metric: dict) -> str:
        value = metric.get(self.key, "not measured")
        return f"{self.key}={value} ({'≥' if self.at_least else '≤'} {self.bound:g})"


@dataclass(frozen=True)
class Verdict:
    state: str              # none | met | blind | converged | unmet
    reason: str = ""


class Targets:
    def __init__(self, targets: list[Target], patience: int = DEFAULT_PATIENCE):
        self.targets = targets
        self.patience = max(1, patience)

    @classmethod
    def from_config(cls, cfg) -> "Targets":
        raw = cfg.get("metric_targets") or {}
        if not isinstance(raw, dict):
            raise ValueError("config: metric_targets must be an object {metric_key: target}")
        targets = [_parse(key, spec) for key, spec in raw.items()]
        return cls(targets, int(cfg.get("convergence_runs", DEFAULT_PATIENCE)))

    def check(self, runs: list[dict]) -> Verdict:
        """`runs` = Store.metric_runs(): [{metric, had_chance}], oldest first."""
        if not self.targets:
            return Verdict("none")
        if not runs:
            return Verdict("unmet", "no metric recorded yet")
        known = {t.key: v for t in self.targets
                 if (v := _last_measured(runs, t.key)) is not None}
        unmet = [t for t in self.targets if not t.met(known.get(t.key))]
        if not unmet:
            return Verdict("met", "goal reached: " + _show(self.targets, known))

        window = runs[-self.patience:]
        blind = [t for t in self.targets if len(runs) >= self.patience
                 and not any(_number(r["metric"].get(t.key)) for r in window)]
        if blind:
            return Verdict("blind",
                           f"cannot measure: {', '.join(t.key for t in blind)} not measured in "
                           f"the last {self.patience} run(s) — fix the metric (key, quota, "
                           "provider) before the loop can judge its goal")

        if all(self._stalled(runs, t) for t in self.targets):
            return Verdict("converged",
                           f"stopped improving: no targeted metric beat its best value over "
                           f"the last {self.patience} run(s) — " + _show(unmet, known))
        return Verdict("unmet", "metric below target: " + _show(unmet, known))

    def _stalled(self, runs: list[dict], target: Target) -> bool:
        """True only with EVIDENCE: the last `patience` chance-runs did not beat the best
        value measured before them. Best, not latest — a judge scores with noise, and one
        low sample at the end must not read as "no movement" (live 2026-10-11: 10.0 then
        9.0 on a site that had just grown a page). A run that had no chance (all actions
        failed or held) does not count toward the window — it changed nothing, so the flat
        metric after it proves nothing."""
        points = [(i, r["metric"][target.key]) for i, r in enumerate(runs)
                  if _number(r["metric"].get(target.key))]
        if not points:
            return False
        end = points[-1][0]
        for cut, _ in reversed(points[:-1]):
            if sum(1 for r in runs[cut:end] if r["had_chance"]) >= self.patience:
                before = target.best([v for i, v in points if i <= cut])
                since = target.best([v for i, v in points if i > cut])
                return target.gain(before, since) <= 0
        return False


def _last_measured(runs: list[dict], key: str) -> Any:
    for r in reversed(runs):
        if _number(r["metric"].get(key)):
            return r["metric"][key]
    return None


def _show(targets: list[Target], known: dict) -> str:
    return ", ".join(t.show(known) for t in targets)


def _parse(key: str, spec: Any) -> Target:
    if _number(spec):
        return Target(key, float(spec), at_least=True)
    if isinstance(spec, dict) and len(spec) == 1:
        (kind, bound), = spec.items()
        if kind in ("min", "max") and _number(bound):
            return Target(key, float(bound), at_least=(kind == "min"))
    raise ValueError(f"config: metric_targets.{key} must be a number (= at least) or "
                     f'{{"min": n}} / {{"max": n}}, got {spec!r}')


def _number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)
