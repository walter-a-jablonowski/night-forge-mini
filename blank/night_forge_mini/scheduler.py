"""`run-loop` — the unattended loop: one pass per tick until told to stop
(tasks/backlog/run-triggers/scheduler-daemon.md).

A thin wrapper by design: everything that decides WHETHER a pass does anything already lives
in `Engine.run_once` — new input, pending work, the metric targets and their stops, anti-spin,
the run lock. A tick on a finished goal is a cheap noop, so the loop keeps polling (new input
may still arrive) instead of exiting on the first STOP.

What the wrapper adds is what only an unattended loop needs:
  backoff   a failed pass (already recorded in the log by the Engine) doubles the wait,
            up to max_backoff, and resets on the next success — a quota or an outage must
            not be hammered every tick
  budget    passes and tokens per rolling 24 h, counted from the log (usage on analysis and
            error records), so a restarted loop sees what the last one spent
  until     a wall-clock end ("07:00") — the night ends even if nobody is up to end it

Nothing here runs a pass itself or prints: `tick` events go to a callback, so the CLI owns
the output and tests can drive a whole night with a fake clock.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

DAY = 24 * 3600


def seconds(value: Any) -> float:
    """`90` / `"90s"` / `"15m"` / `"1h"` -> seconds."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smh]?)\s*", str(value))
    if not m:
        raise ValueError(f"not a duration: {value!r} (use e.g. 90s, 15m, 1h)")
    return float(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600}[m.group(2)]


def next_clock_time(hhmm: str, now: datetime) -> datetime:
    """The next local `HH:MM` after `now` — tonight's 23:00, or tomorrow's 07:00."""
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", hhmm)
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ValueError(f"not a clock time: {hhmm!r} (use HH:MM)")
    at = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
    return at if at > now else at + timedelta(days=1)


@dataclass
class Schedule:
    interval: float = 900.0          # seconds from the end of one tick to the next
    until: datetime | None = None    # local wall-clock end
    ticks: int = 0                   # stop after this many ticks; 0 = no limit
    passes_per_day: int = 0          # rolling 24 h, counted from the log; 0 = no limit
    tokens_per_day: int = 0          # input + output, rolling 24 h; 0 = no limit
    max_backoff: float = 3600.0

    @classmethod
    def from_config(cls, cfg, interval=None, until=None, ticks=None) -> "Schedule":
        """Config `schedule` block, then the command line on top."""
        block = cfg.get("schedule") or {}
        until_s = until if until is not None else block.get("until") or ""
        return cls(interval=seconds(interval if interval is not None
                                    else block.get("interval", "15m")),
                   until=next_clock_time(until_s, datetime.now()) if until_s else None,
                   ticks=int(ticks if ticks is not None else block.get("ticks", 0)),
                   passes_per_day=int(block.get("passes_per_day", 0)),
                   tokens_per_day=int(block.get("tokens_per_day", 0)),
                   max_backoff=seconds(block.get("max_backoff", "1h")))


class Scheduler:
    def __init__(self, engine, schedule: Schedule, on_tick: Callable[[dict], None],
                 now: Callable[[], datetime] = datetime.now,
                 sleep: Callable[[float], None] = time.sleep):
        self.engine = engine
        self.schedule = schedule
        self.on_tick = on_tick
        self.now = now
        self.sleep = sleep

    def run(self) -> dict[str, Any]:
        """Tick until `until`, `ticks`, or Ctrl+C. Returns the session summary."""
        s = self.schedule
        summary = {"ticks": 0, "ran": 0, "failed": 0, "noop": 0, "skipped": 0,
                   "stopped": ""}
        failures = 0
        try:
            while True:
                if s.until and self.now() >= s.until:
                    summary["stopped"] = f"reached {s.until:%H:%M}"
                    break
                if s.ticks and summary["ticks"] >= s.ticks:
                    summary["stopped"] = f"{s.ticks} tick(s) done"
                    break
                summary["ticks"] += 1
                event = self._tick(summary["ticks"])
                summary[event["kind"]] += 1
                failures = failures + 1 if event["kind"] == "failed" else 0
                self.on_tick(event)
                wait = s.interval if not failures else \
                    min(s.interval * 2 ** failures, max(s.interval, s.max_backoff))
                if s.until:
                    wait = min(wait, max(0.0, (s.until - self.now()).total_seconds()))
                if s.ticks and summary["ticks"] >= s.ticks:
                    continue                 # the last tick: no wait after it
                self.sleep(wait)
        except KeyboardInterrupt:
            # a pass interrupted mid-way leaves its actions HELD, never half-run (the gate
            # runs after the proposal is written) — see the 2026-10-11 sleep incident
            summary["stopped"] = "interrupted"
        return summary

    def _tick(self, n: int) -> dict[str, Any]:
        event: dict[str, Any] = {"tick": n, "at": self.now()}
        over = self._over_budget()
        if over:
            return {**event, "kind": "skipped", "reason": over}
        try:
            result = self.engine.run_once()
        except Exception as e:  # noqa: BLE001 - recorded in the log by the Engine already
            return {**event, "kind": "failed", "error": f"{type(e).__name__}: {e}"}
        if result.get("status") == "ok":
            return {**event, "kind": "ran", "result": result}
        kind = "skipped" if result.get("busy") else "noop"
        return {**event, "kind": kind, "result": result, "reason": result.get("reason", "")}

    def _over_budget(self) -> str:
        s = self.schedule
        if not (s.passes_per_day or s.tokens_per_day):
            return ""
        since = (datetime.now(timezone.utc) - timedelta(seconds=DAY)).isoformat(timespec="seconds")
        spent = self.engine.store.spent_since(since)
        if s.passes_per_day and spent["passes"] >= s.passes_per_day:
            return f"budget: {spent['passes']} passes in the last 24 h (limit {s.passes_per_day})"
        if s.tokens_per_day and spent["tokens"] >= s.tokens_per_day:
            return f"budget: {spent['tokens']} tokens in the last 24 h (limit {s.tokens_per_day})"
        return ""
