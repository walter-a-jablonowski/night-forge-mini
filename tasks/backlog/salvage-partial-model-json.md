# Salvage a partial parse when every JSON attempt fails

Split out of `llm-json-retry.md` (done 2026-09-04, see `tasks/v done/`), which built the
bounded retry and deliberately left this as the next rung.

**Effort: S.** Confined to `_extract_json` / `_request_json` in `llm.py`.

## Where it bites
The retry already covers the common case — live evidence: run-a257a9c6 fired two
`json_retry` spans and still finished with 5/5 actions. What is not covered is the run where
all three attempts come back malformed. Today that raises `LLMError` and the pass is lost,
*after* its tool budget has been spent: in the failures that motivated the retry, the model
had made four `read_page` calls before emitting the proposal. Re-running repeats every one of
those reads.

## Why a partial answer is safe to accept
The core already treats model output as untrusted: `sanitize_actions` drops malformed actions
(logging them as `dropped`), and `risk_level` / `reversible` always come from the pack, never
from the reply. So a half-parsed proposal cannot weaken the gate — the worst case is fewer
actions than the model intended, which is exactly what happens today, only today the number
is zero.

## Shape
When the last attempt still fails, try to recover objects rather than the whole document:
- scan for balanced `{…}` objects inside the `actions` array and keep the ones that parse,
- keep the `finding` string if it parses on its own,
- return `{"finding": …, "actions": [<the ones that survived>]}` and record what was lost.

Log the salvage explicitly (a span like the `json_retry` one, or a `dropped` entry on the
proposal record). A silent partial result is worse than a loud failure — the operator must be
able to see that the run acted on a fragment.

## Careful
- Salvage only after the retries are exhausted, never as the first parse path: a model that
  gets one clean chance produces better output than one whose sloppiness is quietly tolerated.
- If nothing at all survives, keep raising. An empty proposal from a parse failure and a
  genuine "nothing to propose" must not look the same in the log.
