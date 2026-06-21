# Self-Improving Closed-Loop System — v1

> Smallest **working** version of [idea.md](idea.md): one domain, the full loop,
> and only the guardrails that are load-bearing on day one. Everything else is
> deferred to `tasks/backlog/` — but v1 includes the extension points so each
> deferred feature slots in without a rewrite.

## v1 Scope (build now)
- **One domain, one goal** (e.g. engineering sprint planning). Generic core, single specialization.
- **Pluggable connectors** — start with 1–2 sources (e.g. tickets + chat export). Interface, not hardcoded.
- **Artifact store** — append-only log of every input, action, decision, outcome. *Also serves as the audit log.*
- **Agent core** — runs the loop: capture → ingest → analyze → **propose**.
- **Propose-only by default** — agent suggests; it does not act on the outside world unentitled.

## Must-do guardrails (in v1, small effort, non-negotiable)
- **Human approval gate** — any irreversible or outward-facing action requires explicit human sign-off. Default mode is suggest, not execute.
- **Append-only audit log** — every action/decision recorded with input + reasoning. Free: it *is* the artifact store.
- **Least-privilege connectors** — each connector gets scoped, read-only-by-default credentials from config. No single all-access key.
- **Cost logging** — record token/API usage per loop run. Visibility before optimization.
- **Graceful degradation** — the manual path always exists. The system augments humans; it is never a hard dependency for getting work done.

## Extension points (cheap to add now, save a rewrite later)
| Prepare in v1 | Unlocks deferred feature |
|---|---|
| Connector = interface (`fetch() -> artifacts`) | More sources, multi-channel capture |
| Action object carries a `risk_level` field | Autonomous low-risk actions |
| Each loop records its `goal` + `metric` | Drift / proxy-metric detection |
| Stable artifact schema (typed, versioned) | Dashboards, ROI attribution |
| Connector credentials abstracted behind config | Full RBAC / data governance |

## The Loop (v1)
1. **Capture** — connectors pull artifacts into the store.
2. **Ingest** — assemble context for the agent (max relevant context).
3. **Analyze** — what happened vs. the stated goal.
4. **Propose** — next plan/actions, each tagged with `risk_level`.
5. **Human gate** — approve / edit / reject. Decision logged.
6. **Improve** — approved outcome feeds back into the next run.

## Explicitly NOT in v1 (see backlog)
- Drift / Goodhart detection → `tasks/backlog/drift-detection.md`
- Full RBAC, retention & data governance → `tasks/backlog/data-governance.md`
- Autonomous (no-review) low-risk actions → `tasks/backlog/autonomous-actions.md`
- ROI / cost-vs-value attribution → `tasks/backlog/roi-measurement.md`
- Software factory (spec+tests, no handwritten code) → `tasks/backlog/software-factory.md`
- Unified cross-domain dashboards → `tasks/backlog/dashboards.md`
- Multi-channel capture (notetaker, agents in all channels) → `tasks/backlog/multi-channel-capture.md`

## Definition of done (v1)
A single specialized loop that ingests real data from ≥1 source, produces a useful
proposal a human approves, logs everything, and gets measurably better as the
artifact history grows — running safely with a human at the gate.
