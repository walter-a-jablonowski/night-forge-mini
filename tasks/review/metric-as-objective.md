# Metric as Objective — predicted vs. actual impact

**From the 2026-07-05 core review.** The difference between "a loop that remembers" and
"a loop that optimizes."

**What:** Make the metric exert pressure on proposals instead of only being recorded:
1. Each proposed action carries an **`expected_impact`** — which metric key it should move,
   in which direction ("kb_entries +1", "stale -2", …). Prompted for in analyze, part of
   the proposal schema.
2. The next run **compares predicted vs. actual**: metric delta since the last run vs. the
   sum of expected impacts of the actions that actually ran. The comparison goes into the
   `history` fed back to the model ("you predicted stale -2, actual was 0 — your
   mark_stale proposals are not landing").

**Why:**
- Since 2026-07-05 the metric trend is fed back, but nothing connects actions to outcomes
  numerically — the model gets no signal about whether its proposals *work*, only whether
  they were approved. Predicted-vs-actual is the cheapest real optimization signal that
  fits the existing loop.
- It is also the substrate the deferred **drift-detection** and **roi-measurement** tasks
  need: both compare expectation against measurement over time.

**Design sketch (fits the existing record shape — no schema change):**
- `expected_impact` lives inside the action dict (proposal payload); `sanitize_actions`
  keeps it optional, no gate involvement.
- A small derived query in `Store` (e.g. `impact_report(n)`): per past run, metric delta
  vs. sum of expected impacts of ran-ok actions; Engine adds it to `history`.
- Packs opt in: a pack whose metric is not action-attributable simply never emits
  `expected_impact`, and the report stays empty.

**Open question:** attribution is fuzzy when several actions run in one pass plus external
changes happen — keep it honest by reporting per-run deltas, not per-action credit.

**Effort:** M (schema + prompt + report query + kb pack adoption).
