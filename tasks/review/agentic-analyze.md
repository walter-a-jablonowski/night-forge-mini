# Agentic Analyze — tool-use loop instead of one-shot completion

**Status: core + kb DONE (2026-07-05).** `ModelWrapper.run_tools(system, user, tools,
schema, max_steps)` — read-only tool loop (function calling), per-call trace logged as
`tool_call` spans under the analysis record, budget-exhaustion forces the structured
proposal, tool errors go back to the model as strings. `Tool` gained a `params` schema
(built-ins covered). kb pack: `read_entry` tool, `analyze_tool_steps` config (0 = one-shot).
Verified live: model read the full entry and MERGED an update instead of overwriting.
Tests: `tests/test_run_tools.py`. **Remains (L):** website-pack adoption, token budget,
quality eval across runs.

**From the 2026-07-05 core review.** The one architectural decision a from-scratch design
would make differently; everything else in /blank survives as-is.

**What:** Turn the inside of the Analyze step from a single one-shot LLM call
(context in → JSON proposal out) into a **bounded agentic tool-use loop**: the model gets
**read-only tools** (read a KB entry / site page in full, search the log, `fetch_url`, …),
iterates until it has what it needs, then emits the **same structured proposal** as today.

**Why:**
- Today the model proposes `edit_entry` against entries it has only seen as 120-char
  previews in the index — it cannot write a good edit for content it never read.
  Keyword-overlap bounded retrieval is a workaround; letting the model pull what it
  decides it needs is the real solution.
- This is where the tool registry earns its keep: currently tools are only called by pack
  code, never by the model. Exposing (whitelisted, read-only) registry tools to the model
  is the natural wiring.

**Explicitly NOT a rewrite:** the outer loop (capture → analyze → propose → gate) and the
propose/act split stay exactly as they are. Only `ModelWrapper` grows a tool-loop mode
(`complete_json` stays for simple packs) and a pack's `analyze` opts in. Write actions
still ONLY happen through the gate — the in-loop tools must be read-only.

**Design sketch:**
- `ModelWrapper.run_tools(system, user, tools, max_steps) -> dict` — provider tool-calling
  API, hard step/token budget, ends by forcing the structured proposal.
- Tools passed in by the pack's analyze: a whitelist of `Tool`s from the registry plus
  pack-local readers (e.g. `read_entry(id)`). Never write tools.
- Each tool call appended to the store as a span record (`parent_id` = analysis record) —
  fits the existing trace shape, pairs with the observability backlog task.

**Effort:** M (wrapper tool loop + kb pack reader tools) → L (website pack, budgets, eval).

**Depends on / pairs with:** structured-output.md (do that first, it is the same call site).
