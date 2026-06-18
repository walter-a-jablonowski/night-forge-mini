# Drift / Proxy-Metric Detection

**What:** Detect when the loop optimizes a proxy that diverges from the real goal
(Goodhart's law), or when the agent's proposals oscillate / overshoot.

**Why deferred:** Needs accumulated metric history and statistical monitoring —
large effort, and meaningless until v1 has produced enough loop runs to compare.

**Value:** Stops a "self-improving" loop from confidently self-amplifying mistakes.

**v1 preparation (already in v1):** Each loop run records its `goal` + `metric`
definition *and* the **measured metric value** in its `analysis` artifact (observed
at Analyze, so it exists even when a run stops at `pending`) — so the time series
already exists. Drift detection reads that history later; no schema change, no backfill.

**Adds later:** ground-truth spot-checks, trend/anomaly alerts on the metric,
auto-pause-and-escalate when divergence crosses a threshold.

**Effort:** L
