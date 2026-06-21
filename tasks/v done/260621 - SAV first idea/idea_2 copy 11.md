# Self-Improving Closed-Loop System — v1

> Smallest **working** version of [idea.md](idea.md): **one hardcoded domain**, the
> full loop, and only the two guardrails that are load-bearing on day one.
> v1 is built from swappable **modules** (clean interfaces) but skips the formal
> packaging/registry — so it stays simple now and upgrades without a rewrite.

## v1 Scope (build now)
- **One hardcoded domain + one goal** (e.g. engineering sprint planning). No multi-domain packaging yet.
- **Fixed core** — loop runner, artifact store (= audit log), approval gate. Small and stable.
- **One connector** — a single source (e.g. tickets export). Written behind the connector interface, not inline.
- **Agent core** — runs the loop: capture → ingest → analyze → **propose** → act.
- **Scoped autonomy** — the agent may run actions on a **config allow-list** (low-risk / reversible) unattended; everything else holds for human sign-off. **Default-deny.**

## Stay modular without over-building (cheap in v1, saves the rewrite)
v1 keeps things swappable through **plain interfaces**, not a registry. Build the seams, defer the framework.
| Seam in v1 (cheap) | Why / what it unlocks later |
|---|---|
| Connector = `fetch() -> artifacts` (one impl, but an interface) | Drop in more sources; later auto-discovery |
| Action = object `{ name, risk_level, reversible, run }` | Gate reads `risk_level`; `reversible` drives later autonomy policy + rollback |
| Goal + metric kept as **data**; each run records the **measured metric value** in its `analysis` artifact (observed at Analyze, before acting) | Builds the time series drift detection + ROI read — no backfill |
| Analysis is a single swappable **function** (context → proposal) | Different strategies per domain later |
| Artifact schema is **typed + versioned**, every record tagged with `domain` (a constant in v1) | Dashboards, per-domain ROI, registry attribution — no re-tagging later |
| Records form a **hierarchical trace** — `run_id` (=trace), `parent_id` (=span parent), and spans carry `start_ts`/`end_ts` | OTel-aligned; renders as a tree/flame graph in Langfuse/LangSmith with no remap |
| Connector creds read from **config** (not inline) | Scoped least-privilege / RBAC later |
| Every model call behind **one thin client wrapper** | Drop-in LLM observability (Langfuse/LangSmith) by config |

> **Deferred on purpose:** the **Domain Pack + registry** (auto-discovered, drop-in
> specializations) is the biggest over-build for v1. Build *one* domain against the
> interfaces above first; extract the pack/registry only when a second domain appears.
> See `tasks/backlog/domain-pack-template.md`.

## Must-do guardrails (in v1 — only the load-bearing two)
- **Policy-driven approval gate** — auto-run requires **both** `action ∈ allow-list` **and** `reversible == true`; otherwise hold for explicit human sign-off. Default-deny. The `reversible == false` block is a **hard floor enforced in code** — a mis-configured allow-list still cannot auto-run an irreversible action.
- **Append-only audit log** — every input/action/decision recorded with reasoning (autonomous *and* approved runs alike). Free: it *is* the artifact store.

*Least-privilege creds and graceful-degradation are v1 principles (read-only key + a TASK), not v1 code. Cost logging is fully deferred — see backlog.*

## The Loop (v1)
1. **Capture** — the connector pulls artifacts into the store.
2. **Ingest** — assemble context for the agent.
3. **Analyze** — what happened vs. the stated goal; record the **measured metric value** in the `analysis` artifact.
4. **Propose** — next plan/actions, each tagged with `risk_level` + `reversible`.
5. **Gate** — allow-listed **and** reversible actions auto-run; the rest wait for human approve / edit / reject. Decision logged either way.
6. **Improve** — not a separate step: each executed action writes an `outcome` (result/status), and the **next run's Ingest reads this accumulated history** — that *is* the improvement.

## Running v1 (operational contract)
How a run actually executes end-to-end — the minimum to make the loop runnable and safe.
- **Trigger** — manual `run-once` (CLI) starts a new loop pass with a fresh `run_id`. Cron/daemon deferred.
- **Async approval (per action)** — within a proposal, each action is gated independently: allow-listed **and** reversible actions run inline; **each held action** becomes a **`pending` action** and the loop stops (it does not block). A proposal may thus have some actions already run and others pending. List them with an `inbox`-style command.
- **`approve`/`reject` resume, they don't start a run** — they append under the **original proposal's `run_id`**, so the trace stays one coherent tree. `approve` writes a `decision` then (after `run()`) an `outcome`; `reject` writes a `decision` only — nothing runs, so there is no `outcome`. Only `run-once` mints a new `run_id`.
- **Approval interface = CLI over the log** — the append-only log *is* the state; an approval is just an appended `decision`. v1 ships a thin CLI (`inbox` / `approve <action_id>` / `reject <action_id>`), no UI/server. **Verdicts are per action**, all going through **one `decide(action_id, verdict, edits?)` function** that writes the `decision` (incl. any edits) and executes — so a later UI / Slack / API is just another caller of `decide()`, never a reimplementation of the gate. See `tasks/backlog/approval-ui.md`.
- **Idempotency guard (at-most-once per logged outcome)** — before running an action, check the store for an existing `outcome` for that `action_id`; skip if present. This makes resume-after-approval and re-runs safe *for the common case*. It is **not** true exactly-once: a crash *between* the side-effect and writing the `outcome` will re-run on retry — so any action that is genuinely unsafe to repeat must be **idempotent on its own side** (e.g. keyed/dedup'd by `action_id`).
- **Failure handling** — wrap each `run()`; on error write an `outcome` with `status: error` + reason and stop that branch. The loop never half-commits silently.
- **Capture dedup** — the watermark is **derived from the log** (the max source-cursor among past `input` records for that connector), so repeated runs ingest only new artifacts. No separate connector-state store — the log stays the single source of truth.
- **Bounded context** — Ingest assembles **recent N runs + same-domain relevant slice**, never the full store. History grows; the context window doesn't.
- **Human-readable output** — every command prints a readable summary of the records it touched: `run-once` shows captured count, the finding + metric vs. goal, and each proposed action with its gate result (auto-ran / pending); `inbox` lists pending actions with rationale + the exact `approve`/`reject` command; a `trace <run_id>` command dumps the whole run as an indented tree. The JSONL log stays the source of truth; these are read-only views over it.

## Artifact record (v1)
One typed shape for every record — the hierarchy is a query (group by `run_id`), not nesting:
```
{ id, run_id, parent_id?, domain, type, ts, start_ts?, end_ts?, source?, payload, schema_v }
```
Closed `type` enum for v1 (one per loop step; extend the enum, never the shape):
| `type` | written at | payload holds |
|---|---|---|
| `input` | Capture | fetched artifacts / source metadata, incl. the **source cursor** (the dedup watermark) |
| `analysis` | Analyze | finding vs. goal + the run's **measured metric value** |
| `proposal` | Propose | actions[] with `risk_level` + `reversible` |
| `decision` | Gate | `auto-run` (allow-list + reversible) or human approve/edit/reject — keyed per `action_id` |
| `outcome` | after an action runs | action **result / `status: ok\|error`** (+ reason) |

## Explicitly NOT in v1 (see backlog)
- Domain Pack + registry packaging (drop-in specializations) → `tasks/backlog/domain-pack-template.md`
- Scoped least-privilege creds / full RBAC & governance → `tasks/backlog/data-governance.md`
- Cost logging, then ROI / cost-vs-value attribution → `tasks/backlog/roi-measurement.md`
- LLM observability — hierarchical tracing (Langfuse/LangSmith preferred), then cost/gateway (Helicone) + OTel export → `tasks/backlog/observability.md`
- Drift / Goodhart detection → `tasks/backlog/drift-detection.md`
- Trusted autonomy beyond a static allow-list (risk classifier + rollback) → `tasks/backlog/autonomous-actions.md`
- Software factory (spec+tests, no handwritten code) → `tasks/backlog/software-factory.md`
- Unified cross-domain dashboards → `tasks/backlog/dashboards.md`
- Multi-channel capture (notetaker, agents in all channels) → `tasks/backlog/multi-channel-capture.md`
- Approval review UI (local web view over the log) → `tasks/backlog/approval-ui.md`

## Definition of done (v1)
A single hardcoded loop that ingests real data from one source, produces a useful
proposal that a human approves (or that safely auto-runs via the allow-list), logs
everything, and gets better as the artifact history grows — running safely with a
human at the gate, and built from modules clean enough to extend without a core rewrite.
