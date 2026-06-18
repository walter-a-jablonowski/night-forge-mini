# LLM Observability (tracing, cost, gateway)

**What:** Bolt industry-standard observability onto the LLM calls — request/response
tracing, token/latency/cost metrics, caching and rate-limit control.

**Preferred: Langfuse / LangSmith** — full **hierarchical trace → nested span** model
(spans, prompts, tokens, latency, eval), the gold standard for agent reasoning trees.
Pick these first; they match our artifact store's trace shape directly.

**Optional add-on: Helicone / Portkey** — gateway/proxy (cost, caching, rate-limiting,
fallbacks). Group requests into sessions but are *not* deep nested-span tracers — add
one only if you need a gateway, alongside (not instead of) the tracer above.

**Why deferred:** This is observability on *model calls*, a different concern from the
artifact store (which logs domain inputs/proposals/approvals/outcomes — the substrate
the loop learns from, and the audit trail). These tools don't replace it. Adopting one
in v1 also overlaps with deferred **cost logging** + **dashboards** and breaks v1's
"runs locally, single JSONL/SQLite, no external service" floor.

**v1 seam (already in v1):** every model call goes through **one thin client wrapper**,
and the artifact store is **already a hierarchical trace** — `run_id` (=trace_id),
`parent_id` (=parent span), and spans carry `start_ts`/`end_ts`. This is the same
trace→nested-span model Langfuse/LangSmith and OpenTelemetry use, so adding
observability later is config, not a rewrite:
- Langfuse/LangSmith → add a callback/decorator inside the wrapper; the store's
  trace tree renders as a tree/flame graph with **no remapping**.
- Helicone/Portkey → change `base_url` + key (only if a gateway is wanted).
- Field names already loosely aligned with **OpenTelemetry GenAI** semantic
  conventions, so an OTel exporter from the artifact store is trivial.

**Adds later:** pick one tracer + (optional) one gateway, wire via the wrapper, emit
existing artifacts to it, dashboards/eval on top.

**Effort:** S (wire one tool via the wrapper) → M (OTel export + dashboards).
