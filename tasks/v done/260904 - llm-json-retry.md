# One malformed JSON response kills the whole run

**Found 2026-09-04** in `try/website/`: two consecutive pending-work runs died with

```
error: LLMError: model did not return valid JSON: Expecting property name enclosed in
double quotes: line 1 column 3418 (char 3417)
error: LLMError: model did not return valid JSON: Expecting ',' delimiter: line 1 column 3916
```

Both times the model had done the right thing — read the site, diagnosed the broken link,
and started emitting a correct `create_page` proposal — and the run was thrown away because
one long payload came back with a JSON defect a few thousand characters in.

**Effort: S.** A bounded retry in `ModelWrapper`.

**✅ DONE 2026-09-04.** `JSON_ATTEMPTS = 3` (one call + two retries) in `llm.py`:
- `_request_json` splits into the retry loop plus `_raw_json_reply` (the call itself), so
  the `response_format` fallback and the retry stay separate concerns.
- Both JSON exit points are covered — the forced finale AND `run_tools`'s "model stopped
  calling tools" path, which is where both live failures actually happened.
- The correction carries the bad reply back plus the parse error, so the retry has the
  context that makes it worth anything.
- Each retry is logged as a `json_retry` span in the same trace the Engine records, so the
  extra call is visible rather than hidden.
- 3 tests, verified failing first; 112 pass.

**Verified live 2026-09-05** — run-a257a9c6 logged **2 `json_retry` spans** (`Expecting ','
delimiter: line 1 column 5496` and a reply with no JSON at all) and still completed with
5/5 actions applied. Before this fix that run would have died twice over; instead the cost
was two extra model calls, visible in the trace.

**Not done:** salvaging a partial action list when all attempts fail — split out as
`backlog/salvage-partial-model-json.md`.

## Not truncation
Checked: an isolated request to the same model returned `finish_reason: stop` and valid
JSON. The provider is not cutting the response off — the model simply emits a malformed
escape/delimiter sometimes when the payload is a long HTML page inside a JSON string. It is
stochastic: earlier runs on the same model produced two full pages plus an image download
without trouble.

## Cause
`_request_json` (`llm.py`) parses once through `_extract_json` and lets `LLMError` propagate.
The only retry that exists is for a provider REJECTING `response_format` (400/422 →
`_param_rejected`), which is a different failure. So a transient formatting slip in the
model's own output is fatal to a pass that may have cost eight tool calls.

## Fix
Retry the JSON completion once or twice when the parse fails, feeding the parse error back
as a corrective message ("your previous reply was not valid JSON: <error>; resend the same
proposal as strict JSON"). Bound it (2 attempts), keep it in `ModelWrapper` so both
`complete_json` and the `run_tools` finale benefit, and log each retry so the cost is visible
rather than hidden.

Worth pairing with salvaging a partial parse when every attempt fails — not built here,
moved to `backlog/salvage-partial-model-json.md`.

## Note
The tool budget is spent BEFORE this failure, so a lost run is not cheap: the model had made
4 `read_page` calls. Retrying the final JSON call is far cheaper than re-running the pass.
