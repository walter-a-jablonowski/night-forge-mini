# notify hook — push, not only pull

**DONE 2026-10-13.** Split out of `approval-ui`: the one part of it that unattended use needs
now. `notify.py` (`Notifier`) + config block `notify` {command, after_failures}; `run-loop`
calls it after every tick and prints what it sent.

**Why:** after the 2026-10-12 real run nothing blocked unattended use except this — the
run-triggers safety note says "don't ship a silent unattended trigger without a notification
path", and `report` only answers when asked. With everything allow-listed holds are rare,
but one cause holds EVERY edit: a dirty git repo in the artifact folder. Unnoticed, the loop
then runs on and achieves nothing.

**What:**
- the channel is the operator's command (popup, mail, webhook) — the core knows none
- told once per condition, not on every tick it persists:
  - `held` — a pass left actions held
  - `failing` — the Nth failed pass in a row (default 3); again only after a success
  - `budget` — the first tick skipped for the daily budget; again only after a tick that was not
- the event arrives as environment variables `NFM_EVENT` / `NFM_MESSAGE` / `NFM_DEPLOY`,
  never pasted into the command text: the message quotes model output and error text
  (tested with `"` `&` `>` in the message — arrives verbatim, nothing executes)
- a failing or hung notifier (30 s timeout) is printed, never raised
- `run-loop` only; `run-once` from an OS scheduler has no notify (README says so)

**Tests:** `test_notify.py` (9): each event, once-per-condition, broken notifier, off by
default, the shell-injection case on the real shell, inside the Scheduler, the CLI end to end.

**Live 2026-10-13:** `try/kb`, `add_entry` taken off the allow-list for one note, command
`powershell -NoProfile -Command "msg $env:USERNAME $env:NFM_MESSAGE"` -> the pass held
`add_entry`, `notified (held): kb: 1 action(s) held for approval (add_entry) - run inbox`,
the next tick (still held) sent nothing. Config restored, action approved and committed.

**Left:** chat/mail channels as ready-made commands, and approve-from-the-message, stay with
[approval-ui](../backlog/approval-ui.md).
