# Scheduler / Daemon — interval poll loop

**DONE 2026-10-11.** `scheduler.py` (`Schedule`, `Scheduler`) + `run-loop` and `report`
commands; config block `schedule` {interval, until, passes_per_day, tokens_per_day,
max_backoff}, overridden by `--interval / --until / --ticks`.
- a thin wrapper, as planned: whether a tick does anything is still `run_once`'s decision
  (input, pending work, targets and their stops, anti-spin, the lock). It keeps polling
  after a STOP, since new input may still arrive.
- backoff: a failed tick doubles the wait up to max_backoff; a success resets it.
- budget: passes / tokens per rolling 24 h, counted from the LOG (`Store.spent_since`), so a
  restarted loop sees what the previous one spent. A tick over budget is skipped.
- until: a local wall-clock end; the last wait is cut to it. Ctrl+C ends with a summary.
- `report --since 12h`: every pass in the window from the log, whoever started it.
Tests: `test_scheduler.py` (13, a whole night on a fake clock, plus the real commands).
Live unattended round 2026-10-11, 19:47-20:52, three deploys at once, `--until 20:52`:

| deploy | ticks | ran / failed / idle | what happened |
|---|---|---|---|
| website (CLI + haiku judge, target 9.5) | 13 | 1 / 0 / 12 | one metric-driven pass (+1 page, $0.089), then `STOP - stopped improving` and idle |
| kb (CLI) | 17 | 2 / 0 / 15 | notes dropped mid-run were picked up next tick: 1 edit; then 2 notes in one tick -> 1 new entry, the duplicate one correctly skipped |
| gemini (HTTP, daily quota gone) | 4 | 0 / 4 / 0 | every tick a recorded 429; waits 6, 12, 24 min (backoff), the last cut by `--until` |

Also live: a manual `run-once` during a loop pass was refused (run lock); all three loops
ended on their own; `report --since 70m` reproduced each night from the log; no held
actions, artifact repos clean.

Pending-notification (held actions piling up unseen) is not built: `report` and the end
summary of `run-loop` show the held count; push notification stays with `approval-ui`.

**What:** Run the loop repeatedly on a timer instead of one manual command — the realistic
"endless loop." Simplest form: `while True: engine.run_once(); sleep(interval)`, exposed as
`run-loop --interval 10m` (or an external cron / systemd timer calling `run-once`).

**Why deferred (idea_2):** v1's trigger is a manual `run-once`; "cron/daemon deferred." Most
domains don't need sub-interval latency — periodic polling of the source (folder, feed) is
enough to "process new stuff as it arrives."

**Value:** Unattended operation. The system keeps capturing + auto-running allow-listed
actions without a human kicking each pass.

**v1 seam (already in v1):** one pass is already a self-contained `run_once()` with a fresh
`run_id`; dedup is derived from the log, so repeated passes ingest only new artifacts. The
daemon is a thin wrapper, not new loop logic.

**Adds later:** `run-loop --interval`, graceful shutdown, backoff when a pass errors, max-runs
/ run-until, optional jitter. External scheduler (cron/systemd/Task Scheduler) needs nothing
new — it just calls `run-once`.

**Safety:** unattended → held actions pile up unseen. Pair with a pending-notification and
allow-list trust — see [README.md](README.md), `../approval-ui.md`, `../autonomous-actions.md`.

**Effort:** S
