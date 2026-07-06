# Cost Logging → ROI / Cost-vs-Value Attribution

**What:** (1) **Cost logging** — record token/API usage per loop run (visibility).
(2) **Attribution** — join that cost to the value each run produced, so spend is
justified by return instead of "token-maxing" on faith.

**Why deferred:** Neither is load-bearing on day one. Raw cost logging is a small,
self-contained add (do it first); value attribution is hard and needs cost + outcome
history, so it comes after.

**Value:** Turns "run an uncomfortably high API bill" into a measured decision —
spend where the loop demonstrably returns more than it costs.

**v1 seam (already in v1):** outcomes/decisions are in the append-only artifact store,
keyed per loop run and tagged with `domain`, and each run records its **measured
metric value** — so cost can be attached per run and joined to value, per domain,
later with no backfill. **Since 2026-07-05 the "value" side is stronger:**
`Store.impact_report(n)` gives per-run predicted-vs-actual metric deltas, so ROI can
join cost against *measured* metric movement, not just raw outcomes. Note the cost side
grew too: agentic analyze (`run_tools`) makes several model calls per run — `tool_call`
spans record each one, but per-call token counts still need capturing (this task).

**Adds later:** per-run cost logging (S), then outcome→cost joins, per-loop/per-domain
ROI reports, budget alerts (L).

**Effort:** S (cost logging) → L (attribution)
