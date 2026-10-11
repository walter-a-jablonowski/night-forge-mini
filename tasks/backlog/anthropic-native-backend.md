# A native Anthropic backend (Messages API) — on demand

Split out of `interchangeable-llms` §6 (archived `v done/261011 - interchangeable-llms.md`).
**Effort: M. Build only when Claude is used over the API seriously** — today Claude runs on
the subscription (`backend: claudeCode`, `one_shot: claudeCode`), which needs none of this.

## Why the OpenAI-compatible endpoint is not enough
Claude is reachable through `HttpBackend` as config only (`base_url
https://api.anthropic.com/v1/` + `ANTHROPIC_API_KEY`), but per Anthropic's docs that endpoint:
- **ignores `response_format`** silently — nothing is constrained; the prompts and the JSON
  retry hold the format instead (`probe` reports it as "ignored by this endpoint"),
- **has no prompt caching** — every tool step resends the whole conversation at full price,
  the amplification measured in `analyze-context-amplification.md` (20-35%),
- returns no thinking, and ignores `strict` on tool schemas.

## Shape
A sibling of `HttpBackend` behind `base.Backend`, registered as e.g. `anthropic`:
- `complete_json` -> Messages API with native structured outputs,
- `run_tools` -> the same bounded loop (`PassBudget`), with `cache_control` on the stable
  prefix (system prompt + context) so later steps read it from cache,
- routable as `one_shot` like any other backend (`backends/routed.py`).

## Before building
Run `probe` against the compatible endpoint first, and measure a pass's cost there — that
number is the case for (or against) the native backend.
