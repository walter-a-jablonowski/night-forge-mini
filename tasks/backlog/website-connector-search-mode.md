# Website connector: `search` mode (phase 3)

Split out of `website-domain-pack.md` (phases 0–2 done 2026-07-28, see `tasks/v done/`). This
is the one unbuilt phase of that pack, and it was always "build only if needed".

**Effort: S.** The core `web_search` tool already exists; this is connector wiring.

## What it would be
Scheduled searches producing input snippets: fixed queries from config, run each pass, results
captured as `input` records the way `pages` mode captures URLs. Today
`domain_pack/__init__.py` raises on any mode other than `pages`.

## Why it is still not built
Model-driven search already covers discovery: `web_search` is handed to the model during
analyze, so it searches when it decides it needs to, and every call is logged as a `tool_call`
span. A scheduled search would add a second, dumber path to the same capability.

## The real objection — it removes quiescence
`pages` mode is naturally bounded: a URL whose content has not changed produces no new
snippet, so the loop goes quiet when there is nothing new. Scheduled searching makes input
effectively **infinite** — there is always another result — so the `seen_ids` watermark stops
bounding runs and only the gate does.

Before building this, the loop needs a stop condition it does not have today:
`backlog/run-when-metric-below-target.md` (goal-reached / metric-target stop). Building search
mode first would produce a system that runs forever by construction.

## If built anyway
- Dedup on result URL + content hash, the same `url#hash` snippet id `pages` mode uses, so a
  repeated hit is not re-ingested.
- Cap results per query per run in config; an unbounded fan-in is the failure mode.
- `web_search` needs `TAVILY_API_KEY` or `EXA_API_KEY`; the connector must degrade to a clear
  config error rather than silently capturing nothing.
