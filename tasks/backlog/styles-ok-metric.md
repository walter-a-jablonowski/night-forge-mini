# Metric `styles_ok` — is the site's CSS actually CSS?

Split out of `write-actions-accept-wrong-file-shape.md` (done 2026-09-05, see
`tasks/v done/`), which fixed the *prevention* half and deliberately left this half unbuilt.

**Effort: S.** One metric module, no core change.

## Why there is anything left to do
The shape floor now refuses an HTML document written to a `.css` target, so the specific way
run-393b4eee destroyed `style.css` cannot recur. What the floor does NOT give is
**visibility**: while that stylesheet held a whole HTML page, every active metric stayed
green — `pages`, `broken_links` and `seo_basics` all reported a healthy site, because the
pages existed, their links resolved and their titles were intact. The site was completely
unstyled and no number said so.

A refusal prevents one known bad write. A metric notices a bad *state*, whoever produced it —
a hand edit, a restore from the wrong commit, a future action, or CSS that is syntactically
fine but semantically ruined (every rule commented out, a truncated payload, an empty file).

## Shape
`domain_pack/metrics/styles_ok.py`, per the metric-module interface:

```python
KEYS = ["styles_ok"]

def measure(site, *, model, goal) -> dict[str, float]:
    ...   # {"styles_ok": <stylesheets that look like working CSS> }
```

A code metric — no model call, so it costs nothing per run and stays deterministic under
`--fake-llm` without a special case.

## What "looks like working CSS" should mean
Keep it cheap and structural; do not pull in a CSS parser for this:
- at least one `selector { … }` rule with a non-empty body,
- balanced braces,
- not an HTML document (reuse the floor's own test rather than restating it).

Report the count of healthy stylesheets, so the number moves when one breaks. A ratio would
hide the difference between "one of one broken" and "one of four broken".

## Open question
Whether `pages` should get the same treatment — a page that is present, linked and titled but
whose body was emptied also scores perfectly today. Same blind spot, one level up; worth
deciding once for both rather than bolting a second metric on later.

## Activation
Not in `DEFAULT_METRICS` until it has run for a while — a new metric that starts red on a
healthy site is worse than no metric. Add it to the deploy config first, watch it, then
promote.
