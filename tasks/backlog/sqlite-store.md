# SQLite Store — when a second writer arrives

**From the 2026-07-05 core review. Trigger-based: do this when scheduler-daemon or
approval-ui (or any second concurrent process) lands — not before.**

**Target version: 0.4.0** — the same release as the first second-writer feature
(scheduler-daemon or approval-ui), so the store design follows its first real consumer.
(0.2.0 = core review fixes; 0.3.0 = website domain pack.)

**What:** Move the append-only log from a single JSONL file to SQLite (one `records`
table, same record shape, still append-only — no updates, no deletes).

**Why (and why not yet):**
- The JSONL file has **no write lock**: REPL + daemon + web inbox appending concurrently
  can interleave lines. SQLite gives locking, atomic appends and indexed queries for free
  (stdlib `sqlite3`, still zero external services — keeps the v1 floor).
- Not yet: single-process use works, and the new per-process cache (2026-07-05) removes
  the reread cost. No second writer exists today.

**Design sketch (the current design ports 1:1):**
- `Store` keeps its exact public surface (`append`, `all`, `of_type`, `seen_snippet_ids`,
  `pending_actions`, `recent_*`, …) — derived-state-by-query is the same idea in SQL.
- One table: `records(id, run_id, domain, type, parent_id, source, start_ts, end_ts, ts,
  schema_v, payload TEXT/JSON)`. Indexes on `run_id`, `type`, `parent_id`.
- WAL mode for concurrent readers + one writer.
- Migration = read old JSONL, insert all rows; keep the JSONL importer around.
- Optional: keep the JSONL backend behind the same interface for zero-dep debugging
  (`paths.log` ending in `.jsonl` vs `.db` selects the backend).

**Effort:** M (backend + migration + the store tests run against both).
