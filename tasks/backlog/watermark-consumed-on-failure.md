# A failed run still consumes its input (watermark advances before analyze)

**Found 2026-09-04** while getting the website pack's first real-model run to complete: the
provider returned 429, and the retry then had nothing to work on.

**Effort: XS–S.** Ordering change in `loop.py` + one test.

## Symptom
```
$ python -m night_forge_mini run-once
error: RateLimitError: 429 … z-ai/glm-5.2:free is temporarily rate-limited upstream
$ python -m night_forge_mini run-once      # (would be) nothing to do: no new snippets
```
The 429 happened in `analyze`, long after the connector had fetched the page — but the input
was already logged, so the snippet counted as seen. Recovering meant deleting
`data/log.jsonl` by hand. A transient provider outage silently costs you the input it was
supposed to process.

## Cause
`Engine.run_once` writes the `input` record (`loop.py:44`) **before** calling
`self.pack.analyze(...)` (`loop.py:58`). `seen_snippet_ids` is derived from those input
records, so the watermark advances on *capture*, while the work that justifies advancing it
happens afterwards and may raise.

Capture-before-analyze is right in itself (the input record is the audit trail of what was
fetched, and it must exist even if analysis later fails). The bug is that **one record serves
two purposes**: "this was fetched" and "this was processed".

## Options
1. **Mark the run's outcome and derive the watermark from processed input** — keep writing the
   input record at capture time, but have `seen_snippet_ids` count only snippets belonging to
   runs that reached a terminal state (analysis logged). A failed run's input is re-offered.
   Most faithful; needs a run-status field the store can filter on.
2. **Write the input record after a successful analyze** — simplest, but loses the record of
   what was fetched when analysis fails, which is exactly the diagnostic you want.
3. **Log a `run_failed` record and let the connector skip it** — the watermark stays
   capture-based, and `seen_snippet_ids` subtracts ids from failed runs. Small, additive, no
   change to the happy path.

(1) or (3). (3) is the cheaper first step and is compatible with (1) later.

## Note
This gets worse with any unattended trigger (`scheduler-daemon`, `filesystem-watch`): nobody
is watching the traceback, and the input is gone. Pairs with `sqlite-store`, where a run
status column is natural.
