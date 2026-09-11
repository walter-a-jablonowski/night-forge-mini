# Claude Code backend — the refinements left after it shipped

Split out of `claude-code-backend.md` (built and live-verified 2026-09-11, see
`tasks/v done/`). Nothing here blocks using the backend; a full analyze pass already runs on
the subscription. These are the edges that were left deliberately.

**Effort: S each, independent of one another.**

## 1. Per-tool span timestamps are all the same
`ClaudeCodeBackend._parse` stamps every span with one `now_iso()` taken at parse time,
because `subprocess.run` buffers the whole stream and only returns when the turn is over —
by then the real timing is gone. HTTP-backend spans carry true per-call start/end, so a
trace mixes honest timings with placeholder ones, which is worse than either.

Fix: read the stream as it arrives (`Popen` + a read loop) and stamp each event when it is
seen. That also removes the need to hold a whole turn in memory. Cost: the timeout handling
gets manual (today `subprocess.run(timeout=...)` does it and kills the child for us), and on
Windows a read loop must not block — the notes in the archived task apply.

Pairs with `observability.md`: a stream-json turn is already a trace, and this is what makes
its spans worth exporting.

## 2. One-shot analyze silently uses the HTTP provider
The analyze/judge split falls on the two protocol methods — `run_tools` goes to the CLI,
`complete_json` to the cheap provider. That is right for a judged metric, but it means a
deploy with `analyze_tool_steps: 0` would run its **analyze** through `complete_json` and so
through the HTTP provider, not the CLI, despite `backend: claudeCode`.

Nothing warns about it today. Options, cheapest first:
- refuse the combination at `build_pack`/Engine time with a clear message,
- or let `ClaudeCodeBackend.complete_json` take a `role` hint so an analyze one-shot still
  goes to the CLI (a turn with no tools — see the guard in §3 below, which would then need
  relaxing for exactly this case).

The first is honest and is probably enough: one-shot mode exists for cheap providers.

## 3. Revisit the no-tools refusal if a pack ever wants a toolless turn
`run_tools` now refuses when no usable tool is offered, because a connected MCP server that
serves nothing leaves the agent exactly as blind as a failed one — and a blind agent invents
rather than failing. That is the right default, but it does hard-code the assumption that an
agent turn always has tools. If a pack ever legitimately wants a toolless CLI turn, this is
the check to revisit — deliberately, not by deleting it.

## 4. Session reuse was decided against — revisit only with evidence
No `--resume`: each run is a fresh CLI session, because our history is already curated and
the cross-run cacheable prefix is only ~856 tokens. Revisit **only** if measurement shows
the per-turn startup (process spawn + MCP handshake + re-reading the artifact) costing more
than the determinism is worth. The archived task carries the reasoning.

## 5. Not measured yet: what a turn actually consumes
Subscription usage is session-based, so there is no per-token bill to read — but we also do
not know how many tool steps a typical pass spends on the CLI versus the HTTP backend, which
is what would tell us whether an unattended daemon is safe. The `tool_call` spans are already
in the log; it is a counting script, not a feature. Do this before `scheduler-daemon`, along
with the stop condition in `run-when-metric-below-target.md`.
