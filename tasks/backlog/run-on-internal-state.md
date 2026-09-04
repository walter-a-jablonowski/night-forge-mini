# A run should be possible when only the ARTIFACT has pending work

**Found 2026-09-04**, website pack real-model run (run-7eb9729b). The loop stopped with
known, recorded work outstanding and no way to resume it.

**Effort: S–M.** Touches `loop.py` (the noop guard) + a pack-side "pending work" signal.

## Symptom
Run 1 wrote an `index.html` linking to `ingredients.html` and `meals.html` that were never
created (see `website-analyze-prompt-tools.md`). The model explicitly deferred them to "a
subsequent run". Run 2, immediately after:

```
$ python -m night_forge_mini run-once
nothing to do: no new snippets
```

The site is left broken and **cannot repair itself**. Every further run is a noop until the
one configured source URL changes upstream.

## Cause
`Engine.run_once` gates the whole pass on connector input (`loop.py:33-36`):

```python
seen = self.store.seen_snippet_ids(connector.name)
snippets = connector.fetch(seen)
if not snippets:
    return {"status": "noop", "reason": "no new snippets"}
```

The premise is *capture-driven*: new external input is the only reason to think. That holds
for the KB pack (nothing to do without new documents) but not for a materialized artifact the
loop **itself** damages or leaves half-finished. The metric knows (`broken_links` would be 2),
the finding says so in plain text, and neither can trigger anything.

## Why this is the inverse of the quiescence worry
The open note on phase 3 (`search` mode) is that unbounded input **removes** quiescence —
the watermark stops bounding runs. This is the same seam failing the other way: the watermark
is *too* strong a stop condition, halting while the goal is measurably unmet. Both say the
same thing — **"new input" is the wrong sole trigger**; the honest one is "new input OR the
artifact is measurably short of the goal".

## Options
1. **Pack-declared pending work** (preferred — no new machinery, keeps the core
   domain-agnostic). Optional `Pack.pending_work(...) -> str | None`; the noop guard becomes
   `if not snippets and not pending:`. The website pack returns a reason when
   `broken_links > 0` or a page referenced by the map is missing; analyze runs with an empty
   snippet list and the reason rendered into the prompt. KB pack does not implement it →
   unchanged behavior.
2. **`--force` flag** on `run-once` — run analyze even with no new snippets. Trivial, but
   operator-driven; does nothing for an unattended daemon.
3. **A metric floor as a run trigger** — run when any active metric is below a configured
   target. More general, and it is the same comparison a goal-reached STOP condition needs
   (see the stop-mechanism note in `-this.md`); build both together or neither.

(1) + (3) are complementary: (1) says "there is work", (3) says "we are not done yet".

## Care
Do not let this become a spin loop: a pass that proposes nothing, or whose actions all fail,
must not immediately re-trigger on the same pending reason. Bound it — no more than one
pending-work run per unchanged artifact state (the site fingerprint is already computable via
`Site`), or a small consecutive-noop-progress counter.
