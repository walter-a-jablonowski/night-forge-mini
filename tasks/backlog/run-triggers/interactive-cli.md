# Interactive CLI — persistent REPL console (Claude-Code-style)

**What:** A persistent interactive session instead of one process per command. The engine +
pack + config load **once**; you get a prompt and issue commands in-session:
`run`, `inbox`, `approve <n>`, `reject <n>`, `edit <n> …`, `trace`, `help`, `quit`. After a
`run`, the pending actions are listed and you act on them **inline** — the same per-action
approve/reject/edit UX Claude Code uses for tool calls.

**Why it's a trigger:** typing `run` fires a pass, and the same session is the human-at-the-
gate. It's the **human-driven, foreground** counterpart to the unattended
[scheduler-daemon](scheduler-daemon.md) / [filesystem-watch](filesystem-watch.md) /
[webhook-trigger](webhook-trigger.md).

**Why deferred:** v1 ships the minimal one-shot CLI (`run-once`/`inbox`/`approve`/`reject`/
`trace`). A REPL + in-session approval prompts is polish, not load-bearing.

**Value:** Tighter human-at-the-gate loop — run → review → approve/edit/reject without
re-invoking; no per-command startup; stateful session; terminal-native **edit-before-approve**
(surfaces the `edits` param the one-shot CLI doesn't expose). Stays within v1's "runs locally,
no server" floor — unlike `../approval-ui.md`'s web view.

**v1 seam (already in v1):** still just a caller of `run_once()` and the one
`decide(action_id, verdict, edits?)`. The REPL is a thin read→dispatch→print loop; the log
stays the source of truth, and edits go through `decide()` (never mutate the log directly).

**Adds later:** command REPL (S) → in-session per-action approve/reject/**edit** prompts +
live/streamed run output (M) → optional natural-language input mapped to commands (M).

**Safety:** foreground + human-driven, so the unattended caveat in [README.md](README.md)
doesn't apply — but edit-before-approve must still funnel through `decide()`.

**Related:** pairs with `../approval-ui.md` (same edit-before-approve, terminal vs. web), same
`decide()` seam.

**Effort:** S (REPL) → M (in-session approval prompts + edit + streaming).
