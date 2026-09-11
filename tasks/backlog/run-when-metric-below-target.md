# Run (and stop) on the metric, not only on input

Split out of `run-on-internal-state.md` (done 2026-09-04, see `tasks/v done/`), which built
option 1 — the pack-declared `pending_work` signal — and left options 2 and 3 unbuilt.

**Effort: M.** Core (`loop.py` + config), plus one metric-target block per deploy config.
Covers the whole of the old `-this.md` "what is missing before a daemon would be safe"
note except the search-mode point, which is `website-connector-search-mode.md`.

## What is already covered, and what is not
`Pack.pending_work` answers **"there is work"** — a concrete, checkable defect in the
artifact (the website pack reports broken internal links). It does not answer **"we are not
done yet"**: a site with zero broken links and `goal_coverage` at 4/10 is intact but far from
its goal, and nothing will run unless the connector happens to bring new input.

## The proposal
Let the config state a target per metric key, and use the comparison twice:

```json
"metric_targets": { "goal_coverage": 8, "seo_basics": 4 }
```

- **as a trigger** — a pass may run with no new input while any active metric is below its
  target,
- **as a STOP condition** — the loop reports "goal reached" when all of them are met, which
  is the thing `-this.md` notes is missing: the metric is measured and logged every run but
  never compared against anything.

One comparison, both directions. That is the reason to build them together rather than
separately — a trigger without a stop condition is a machine that never rests, and a stop
condition without a trigger only ever fires by accident.

## The second stop condition: CONVERGENCE (folded in 2026-09-11)
"Not done yet" and "not getting anywhere" are different, and only the first is covered
above. A metric that sits below its target and never moves would keep triggering runs
forever — the target check alone gives a daemon that grinds on a plateau, which is the
failure the original `-this.md` note called out as *"N consecutive runs with no metric
improvement does not halt anything"*.

So the same recorded metric history answers a second question: **has any active metric
improved in the last N runs?** If not, stop and say so — the reason matters, because
"goal reached" and "stopped improving" call for opposite responses from the operator
(accept, versus change the goal, the tools or the model).

`Store.recent_metrics(n)` already holds everything needed; N belongs in config beside the
targets (3 is a reasonable default — two passes can legitimately produce no measurable
change while setting up a third).

Care:
- Compare only the metrics that HAVE targets. A metric nobody set a target for is being
  watched, not pursued, and it must not veto a run by failing to move.
- Some metrics legitimately plateau at their ceiling (`seo_basics` = every page has a
  title). Reaching a target must be checked BEFORE no-improvement, or a finished site
  halts with "stopped improving" instead of "goal reached".
- A run whose actions all failed has not had the chance to improve anything; count it as
  a failed run, not as evidence of convergence.

## Anti-spin is NOT this
`Store.last_run_made_progress()` guards the `pending_work` trigger and must guard the
metric trigger too. But be clear what it is: a ONE-run check that asks whether the previous
pass captured input or ran an action successfully. It never looks at the metric, and it
does not apply to input-driven runs. It stops a pointless immediate repeat; it does not
detect convergence. Both are needed, and they are not substitutes.

## Ordering problem to solve first
The metric is measured *inside* `analyze`, i.e. only once a pass is already running. A
trigger needs the value *before* deciding to run. Options: reuse the previous run's recorded
metric (cheap, one run stale — probably fine), or let the pack expose the code-metric subset
cheaply the way `pending_work` already does (`goal_coverage` is LLM-judged, so it must not be
measured just to decide whether to think).

## Lesser alternative, if this proves too much
A `--force` flag on `run-once` that runs analyze despite no new snippets. Trivial to build,
but operator-driven — it does nothing for an unattended daemon, which is where the missing
stop condition actually hurts. Worth having as a debugging convenience, not as the answer.

## Pairs with
`scheduler-daemon` (an unattended loop is what makes a stop condition urgent) and
`drift-detection` (same recorded-metric substrate).
