# Filesystem Watch — fire a run on a new artifact

**What:** Event-driven trigger: watch the connector's source directory and call `run_once()`
when a file is added/changed, instead of polling on a timer. Natural fit for the KB demo's
`text-folder` connector (`data/inbox/`). E.g. via `watchdog`.

**Why deferred:** v1 is manual. Watching is only worth it over a [scheduler-daemon](scheduler-daemon.md)
poll when you want low latency (act the moment a file lands) and polling feels wasteful.

**Value:** Near-instant reaction to new input with no busy-polling; good demo of true
event-driven capture.

**v1 seam (already in v1):** the connector interface is `fetch(seen_ids) -> artifacts` and
dedup is log-derived, so a watcher just calls `run_once()` on a change — the loop figures out
what's new. Watching is **per-connector**: only sources that are watchable (a folder) qualify;
others use poll or webhook.

**Adds later:** debounce/coalesce bursts of file events into one run, ignore temp/partial
writes, optional glob filter. Could live as a small runner alongside the pack, or a connector
capability (`watch()`), without core changes.

**Safety:** same unattended caveat as the daemon — see [README.md](README.md).

**Effort:** S
