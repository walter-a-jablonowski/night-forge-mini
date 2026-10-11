# A failed pass must leave a record in the log

**DONE 2026-10-11.** `error` record type (`records.py`); `Engine.run_once` wraps the pass
(`_pass`) and on an exception appends `error` {stage, error, usage} plus the tool spans the
backend had collected, then re-raises — `run-once` keeps exit code 1. Stages: capture ·
analyze · propose · gate. Writing the record never masks the original error.
`last_run_made_progress` skips failed runs, so a transient failure cannot block the next
metric-driven pass. `trace` shows `FAILED in <stage>: …` with the usage; `report` lists it.
Tests: `test_unattended_guards.py` (5 of 9). Live: `try/gemini` under `run-loop`, daily
quota exhausted — every tick a recorded `RateLimitError` in stage analyze.

**Effort: S. Blocks unattended use** (0.4.0, before `scheduler-daemon`).

## The gap
A pass that raises — LLM unreachable, quota (429), a refused CLI turn, a connector that
cannot fetch — prints `error: …` to stderr, exits 1, and leaves the log with at most an
orphan `input` record. Seen live 2026-10-11 on `try/gemini` (three 429 failures in a row).

Supervised, a human reads stderr. Unattended (a timer, Task Scheduler, `run-loop`), nobody
does: a night of failures is indistinguishable from a night with nothing to do. The pass's
token usage is lost with it (`roi-measurement`'s known gap).

## Shape
- a new record type `error` under the pass's run_id: the stage it died in (capture ·
  analyze · propose · gate · git), the error type and message, and the usage / tool spans
  the backend had collected by then,
- the exception still propagates — `run-once` keeps its exit code 1,
- a failed run is NOT "a pass that made no progress": anti-spin must skip it, or one
  transient 429 would block every later metric-driven pass until new input arrives.

## Done when
A crashed pass shows up in `trace` and in the morning `report` with its reason and cost.
