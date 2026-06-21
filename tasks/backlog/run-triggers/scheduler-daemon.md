# Scheduler / Daemon — interval poll loop

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
