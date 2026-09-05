# Round metric values for the CLI line

Split out of `website-analyze-prompt-tools.md` (done 2026-09-04, see `tasks/v done/`), where
it was noted as a minor observation from the same run.

**Effort: XS.** Display only, in the CLI's run summary.

## What it looks like
```
metric     : pages=1  broken_links=0  seo_basics=0  goal_coverage=1e-16  incoming_new=1
```

The `goal_coverage` judge answered with a tiny float instead of `0`. The metric module is
correct — `max(0.0, min(10.0, float(score)))` clamps it, and `1e-16` is a truthful reading of
what the model said. It is only the presentation: `1e-16` reads as a bug or a broken metric
at a glance, when it means "zero".

## Fix
Round metric values where the CLI prints them, not where they are measured — the log must
keep the exact value it recorded, since `impact_report` diffs consecutive metrics and
rounding at the source would quietly change those deltas.

Two decimals is enough for every metric shipped (three are integer counts, one is a 0–10
judge score).

## Related
The same judge produced a 64714-digit number on another run, which was a real crash rather
than a display nit — fixed separately, see `tasks/v done/260905 -
json-parse-failures-must-be-retryable.md`. Both come from the same place: a free-text judge
can return any number at all, so the code around it should be defensive about the value and
honest about what it displays.
