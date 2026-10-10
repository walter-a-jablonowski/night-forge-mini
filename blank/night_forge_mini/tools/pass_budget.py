"""Per-pass hygiene for the tool results of one analyze pass — shared by every backend.

Every step of an agentic pass resends the whole conversation, so a tool result is not paid
for once but once per remaining step (measured 4-6x on the website deploy, see
tasks/backlog/analyze-context-amplification.md). Two guards follow from that, and they must
hold whichever backend runs the pass:

  repeat   an identical (tool, args) call is answered with a pointer to the earlier result,
           not the body again. Safe because analyze tools are READ-ONLY and nothing writes
           during a pass, so the answer cannot have changed.
  take     `cap` bounds one result, `remaining` the SUM of all of them; a trimmed result
           SAYS it was trimmed, so the model does not mistake a cut file for a short one.

The HTTP backend applies this inside its own loop. The Claude Code CLI runs the loop itself,
so there the MCP server applies it — that process lives exactly one CLI turn, which makes
its state the pass state. Built in one place because the first version lived only in the
HTTP backend, and the CLI then re-read one page five times in a single pass.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

RESULT_CAP = 16_000       # one result
RESULT_BUDGET = 40_000    # the sum of a pass's results

# how a repeat answer starts — public so a trace reader can recognise one
ALREADY_READ = "(already read above in this pass"


@dataclass
class PassBudget:
    cap: int = RESULT_CAP
    remaining: int = RESULT_BUDGET
    seen: dict[tuple[str, str], int] = field(default_factory=dict)  # call -> size returned

    def repeat(self, name: str, args: dict) -> str | None:
        """The pointer to send instead of a body this pass has already received, or None."""
        if _key(name, args) not in self.seen:
            return None
        return f"{ALREADY_READ} — see the earlier {name} result; it has not changed)"

    def size_of(self, name: str, args: dict) -> int:
        """The honest size of an earlier answer, for the trace of a repeat."""
        return self.seen.get(_key(name, args), 0)

    def remember(self, name: str, args: dict, size: int) -> None:
        """Mark a call as answered. Only successful calls: a failed one may succeed on retry."""
        self.seen[_key(name, args)] = size

    def take(self, result: str) -> str:
        """What of `result` may go into the prompt — trimmed, and SAID to be trimmed."""
        allowed = min(self.cap, max(self.remaining, 0))
        if len(result) <= allowed:
            self.remaining -= len(result)
            return result
        dropped = len(result) - allowed
        note = f"\n… trimmed: {dropped:,} more characters (per-pass result budget reached)"
        self.remaining -= allowed
        return result[:max(allowed - len(note), 0)] + note


def _key(name: str, args: dict) -> tuple[str, str]:
    return name, json.dumps(args, sort_keys=True)
