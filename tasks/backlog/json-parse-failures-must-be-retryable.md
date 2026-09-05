# A parse failure that is not JSONDecodeError escapes the JSON retry

**Found 2026-09-05**, run-a257a9c6. The `goal_coverage` judge answered with a number of
**64714 digits**, and the run logged:

```
[metric errors: goal_coverage: ValueError: Exceeds the limit (4300 digits) for integer
 string conversion: value has 64714 digits]
```

**✅ DONE 2026-09-05.** Effort was XS.

## What was wrong
`json.loads` on a huge integer literal raises a **bare `ValueError`** from `int()`, not
`json.JSONDecodeError` (verified: `isinstance(e, JSONDecodeError)` is False). `_extract_json`
caught only `JSONDecodeError`, so this escaped the tolerant fallback AND the new JSON retry
(`llm-json-retry.md`), and surfaced as a crashed metric instead of a second attempt.

Failure isolation did its job — `measure_all` skipped the module, its key was omitted, the
error was recorded in the finding, and the run completed with its other four metrics. So the
blast radius was correct; the recovery was simply never attempted.

## Fix
- `_extract_json` catches `ValueError` (which covers `JSONDecodeError`, a subclass), so every
  parse failure leaves as the `LLMError` the retry is watching for.
- Added `_as_object`: valid JSON that is not an object is also a parse failure, since every
  caller expects a dict — a bare array used to escape as a surprise type.
- Verified end-to-end: the exact 64714-digit reply now costs one `json_retry` span and the
  second attempt returns `{"score": 8, ...}`.
- 2 tests, written failing first; 114 pass.
