"""Tell a human when an unattended loop needs one (tasks/v done/261013 - notify-hook.md).

`report` answers when asked; this is the push half. Without it a deploy whose actions HOLD
(a dirty git repo makes every edit hold) or whose passes keep failing does nothing useful
until someone happens to look — the "silent unattended trigger" the run-triggers README
warns about.

The channel is the operator's own command (config `notify.command`): a popup, a mail, a chat
webhook — the core knows none of them. It gets the event as ENVIRONMENT variables, never as
text pasted into the command line: the message quotes model output and error text, and a
quote or `&` in it must not become shell syntax.

  NFM_EVENT    held | failing | budget
  NFM_MESSAGE  one line for a human
  NFM_DEPLOY   the deploy's folder name

Each condition is told once, not on every tick it persists:
  held     a pass that left actions held (the next pass's new holds are a new event)
  failing  the Nth failed pass in a row; told again only after a success broke the streak
  budget   the first tick skipped for the daily budget; again only after a tick that was not
"""
from __future__ import annotations

import os
import subprocess
from typing import Any, Callable

TIMEOUT = 30    # seconds — a hung notifier must not stall the loop


class Notifier:
    def __init__(self, command: str, deploy: str = "", after_failures: int = 3,
                 run: Callable[..., Any] = subprocess.run):
        self.command = command
        self.deploy = deploy
        self.after_failures = max(1, after_failures)
        self.run = run
        self.failures = 0
        self.budget_told = False

    @classmethod
    def from_config(cls, cfg) -> "Notifier | None":
        """None when no command is configured — notification is opt-in."""
        block = cfg.get("notify") or {}
        command = str(block.get("command") or "").strip()
        if not command:
            return None
        return cls(command, deploy=cfg.root.name,
                   after_failures=int(block.get("after_failures", 3)))

    def observe(self, event: dict) -> str:
        """Look at one run-loop tick; notify if it calls for it. Returns a line for the
        loop's output ("" when nothing was sent) — a failed notification is reported
        there, never raised: the loop matters more than its messenger."""
        told = self._event(event)
        if not told:
            return ""
        kind, message = told
        return self._send(kind, message)

    def _event(self, event: dict) -> tuple[str, str] | None:
        kind = event["kind"]
        self.failures = self.failures + 1 if kind == "failed" else 0
        budget = kind == "skipped" and str(event.get("reason", "")).startswith("budget:")
        first_budget_skip = budget and not self.budget_told
        self.budget_told = budget

        if kind == "failed" and self.failures == self.after_failures:
            return "failing", (f"{self.deploy}: {self.failures} pass(es) failed in a row - "
                               f"last: {event['error'][:200]} - see `report`")
        if first_budget_skip:
            return "budget", (f"{self.deploy}: {event['reason']} - passes are skipped "
                              "until it frees up")
        if kind == "ran" and event["result"].get("pending"):
            held = event["result"]["pending"]
            names = ", ".join(sorted({a["name"] for a in held}))
            return "held", (f"{self.deploy}: {len(held)} action(s) held for approval "
                            f"({names}) - run `inbox`")
        return None

    def _send(self, kind: str, message: str) -> str:
        env = {**os.environ, "NFM_EVENT": kind, "NFM_MESSAGE": message,
               "NFM_DEPLOY": self.deploy}
        try:
            done = self.run(self.command, shell=True, env=env, timeout=TIMEOUT,
                            capture_output=True, text=True)
        except Exception as e:  # noqa: BLE001 - timeout, missing shell: report, carry on
            return f"notify failed ({kind}): {type(e).__name__}: {e}"
        if done.returncode:
            detail = (done.stderr or done.stdout or "").strip()[:200]
            return f"notify failed ({kind}): exit {done.returncode} {detail}".rstrip()
        return f"notified ({kind}): {message}"
