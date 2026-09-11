
Not placed below

- `__version__` still says 0.2.3, so the last two releases are unnumbered in code. Decide
  whether the Claude Code release is 0.3.1 or 0.4.0 before cutting it — bookkeeping, not a
  backlog item.
- `mcp_server.py` reports its own version as "0.3.0" to MCP clients; keep it in step with
  `__version__` whichever number is chosen.

Version, then the tasks that make it up, each in priority order (effort in parens).
Reorganised 2026-09-11 after the Claude Code backend.

**0.2.0 / 0.2.1 — Fable 5 review — DONE** (0.2.1 = REPL robustness + LLM timeout/retries)

**0.3.0 — website domain pack — DONE 2026-07-28** (phases 0-2)
  [text](v%20done/260728%20-%20website-domain-pack.md)

**0.3.x — LLM backend seam + Claude Code on the user's subscription — DONE 2026-09-11**
  [text](v%20done/260911%20-%20claude-code-backend.md)

**0.3.x (next) — instrument and finish what just shipped.** No new seam; this is the
release that makes the last two legible and pays off their loose ends.

0. long-run findings (2026-09-11) — 6 bugs from 5 live passes on an unfamiliar topic;
   5 fixed, 1 deliberately downgraded. The record of what was wrong and why, kept
   because most of it is not visible from the diffs alone.
   [text](backlog/long-run-2026-09-11.md)
1. observability (S) — wire one tracer through the backend seam: one call site per
   backend, and the store is already trace-shaped. A Claude Code turn IS a trace
   (stream-json). [text](backlog/observability.md)
2. roi-measurement / cost logging (S) — still no answer to "what does a run cost". A
   subscription turn has no token bill, so the first step is counting what the spans
   already record. [text](backlog/roi-measurement.md)
3. analyze-context-amplification (S-M) — **unblocked**: lever 1 waited for the backend
   seam, which has landed. 20-35% measured on the HTTP path; levers 2+3 are done.
   [text](backlog/analyze-context-amplification.md)
4. claude-code-backend-refinements (S each) — per-tool span timestamps (needed by 1), the
   one-shot/HTTP combination, measuring a turn's cost (feeds 2).
   [text](backlog/claude-code-backend-refinements.md)
5. salvage-partial-model-json (S) — when every JSON retry fails, keep what parsed instead
   of losing a pass whose tool budget is already spent.
   [text](backlog/salvage-partial-model-json.md)
6. website pack polish — [text](backlog/styles-ok-metric.md) (S; no metric notices a
   structurally broken stylesheet) · [text](backlog/metric-display-rounding.md) (XS;
   `goal_coverage=1e-16` reads as a bug).

**0.4.0 — unattended operation.** The first second-writer feature together with
sqlite-store, so the storage is designed around its first real consumer.

1. run-when-metric-below-target (M) — **the prerequisite for everything else here.** The
   metric is measured every run and compared to nothing, so the loop cannot say "done".
   Do not ship a daemon without it. [text](backlog/run-when-metric-below-target.md)
2. scheduler-daemon (S) — the realistic unattended loop; the first candidate second
   writer. [text](backlog/run-triggers/scheduler-daemon.md)
3. approval-ui (S read-only) — web inbox over the log; the other candidate second writer,
   and it lowers the cost of keeping a human at the gate. Matters most for the website
   pack (diffs for overwrite/delete). [text](backlog/approval-ui.md)
4. sqlite-store (M) — pulled in by whichever of 2/3 lands first.
   [text](backlog/sqlite-store.md)
5. filesystem-watch (S) — event-driven trigger; fits the KB folder.
   [text](backlog/run-triggers/filesystem-watch.md)
6. data-governance (S first step) — scoped read-only creds per connector, and now a second
   credential KIND: a subscription-backed backend has no api key at all. Unattended running
   is what makes this urgent. [text](backlog/data-governance.md)

**0.5.0 — reachable from outside the box.** Everything here assumes 0.4.0's storage and
notification story exists.

1. http-api-server (M) — HTTP over the engine; substrate for web UI, remote, webhooks.
   [text](backlog/run-triggers/http-api-server.md)
2. webhook-trigger (M) — an external event fires a run; builds on http-api-server.
   [text](backlog/run-triggers/webhook-trigger.md)
3. library-embed (XS) — in-process use already works; the task is documenting and
   hardening it as a supported entry point.
   [text](backlog/run-triggers/library-embed.md)
4. interactive-cli-editing (M) — the REPL's remaining half: edit-before-approve +
   streaming. Overlaps approval-ui — decide which surface is primary first.
   [text](backlog/run-triggers/interactive-cli-editing.md)

**1.0.0 — core-as-package**, because pip-installing the core is the moment the Pack seam
becomes a frozen public API — the honest definition of 1.0 for this project.

1. core-as-package (S first step DONE) — [text](backlog/core-as-package.md)

**Unscheduled — build only when the trigger fires.** These are not "later", they are
"when X happens"; each file names its X.

- website-connector-search-mode (S) — website pack phase 3. Gated on the 0.4.0 stop
  condition: scheduled search makes input effectively infinite, so the watermark stops
  bounding runs. Build only if model-driven search proves insufficient.
  [text](backlog/website-connector-search-mode.md)
- autonomous-actions (M) — the general version (risk classifier + rollback), once
  hand-curating the allow-list hurts. 0.3.0 shipped the first concrete instance
  (git-backed autonomy). [text](backlog/autonomous-actions.md)
- drift-detection (L) — substrate exists (impact_report); needs accumulated history before
  the statistics mean anything. [text](backlog/drift-detection.md)
- embedding-retrieval (M, likely never) — agentic reads supersede it; the trigger is an
  index too large to list even as a slice. [text](backlog/embedding-retrieval.md)
- git-library (deferred) — the CLI variant shipped; swapping to a library did not.
  [text](backlog/git-library.md)
- multi-channel-capture (L) — many integrations + consent.
  [text](backlog/multi-channel-capture.md)
- dashboards (L) — only pays off with multiple domains. [text](backlog/dashboards.md)
- software-factory (XL) — separate, huge specialization.
  [text](backlog/software-factory.md)

done (all in tasks/v done/): structured-output · agentic-analyze · metric-as-objective ·
bounded-retrieval · tool-registry · stale-edit-guard · interactive-cli (REPL half) ·
git-integration · website-domain-pack (phases 0-2) · llm-json-retry ·
run-on-internal-state · hard-constraints-bypassable-by-action-choice ·
website-analyze-prompt-tools · write-actions-accept-wrong-file-shape ·
json-parse-failures-must-be-retryable · website-action-precondition-confusion (no fix
needed) · claude-code-backend
