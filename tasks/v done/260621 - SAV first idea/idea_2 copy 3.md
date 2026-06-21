# Self-Improving Closed-Loop System — v1

> Smallest **working** version of [idea.md](idea.md): **one hardcoded domain**, the
> full loop, and only the two guardrails that are load-bearing on day one.
> v1 is built from swappable **modules** (clean interfaces) but skips the formal
> packaging/registry — so it stays simple now and upgrades without a rewrite.

## v1 Scope (build now)
- **One hardcoded domain + one goal** (e.g. engineering sprint planning). No multi-domain packaging yet.
- **Fixed core** — loop runner, artifact store (= audit log), approval gate. Small and stable.
- **One connector** — a single source (e.g. tickets export). Written behind the connector interface, not inline.
- **Agent core** — runs the loop: capture → ingest → analyze → **propose**.
- **Propose-only** — the agent suggests; it never acts on the outside world without human sign-off.

## Stay modular without over-building (cheap in v1, saves the rewrite)
v1 keeps things swappable through **plain interfaces**, not a registry. Build the seams, defer the framework.
| Seam in v1 (cheap) | Why / what it unlocks later |
|---|---|
| Connector = `fetch() -> artifacts` (one impl, but an interface) | Drop in more sources; later auto-discovery |
| Action = object `{ name, risk_level, run }` | Gate reads `risk_level`; later autonomous low-risk actions |
| Goal + metric kept as **data**, not hardcoded in the loop | Swap domains; later drift / proxy-metric detection |
| Analysis is a single swappable **function** (context → proposal) | Different strategies per domain later |
| Artifact schema is **typed + versioned** | Dashboards, ROI attribution, governance per type |
| Connector creds read from **config** (not inline) | Scoped least-privilege / RBAC later |

> **Deferred on purpose:** the **Domain Pack + registry** (auto-discovered, drop-in
> specializations) is the biggest over-build for v1. Build *one* domain against the
> interfaces above first; extract the pack/registry only when a second domain appears.
> See `tasks/backlog/domain-pack-template.md`.

## Must-do guardrails (in v1 — only the load-bearing two)
- **Human approval gate** — any irreversible or outward-facing action requires explicit human sign-off. Default is suggest, not execute.
- **Append-only audit log** — every input/action/decision recorded with reasoning. Free: it *is* the artifact store.

*Least-privilege creds, cost logging, and graceful-degradation are v1 principles (read-only key + a TODO), not v1 code — see backlog.*

## The Loop (v1)
1. **Capture** — the connector pulls artifacts into the store.
2. **Ingest** — assemble context for the agent.
3. **Analyze** — what happened vs. the stated goal.
4. **Propose** — next plan/actions, each tagged with `risk_level`.
5. **Human gate** — approve / edit / reject. Decision logged.
6. **Improve** — approved outcome feeds back into the next run.

## Explicitly NOT in v1 (see backlog)
- Domain Pack + registry packaging (drop-in specializations) → `tasks/backlog/domain-pack-template.md`
- Scoped least-privilege creds / full RBAC & governance → `tasks/backlog/data-governance.md`
- Cost logging, then ROI / cost-vs-value attribution → `tasks/backlog/roi-measurement.md`
- Drift / Goodhart detection → `tasks/backlog/drift-detection.md`
- Autonomous (no-review) low-risk actions → `tasks/backlog/autonomous-actions.md`
- Software factory (spec+tests, no handwritten code) → `tasks/backlog/software-factory.md`
- Unified cross-domain dashboards → `tasks/backlog/dashboards.md`
- Multi-channel capture (notetaker, agents in all channels) → `tasks/backlog/multi-channel-capture.md`

## Definition of done (v1)
A single hardcoded loop that ingests real data from one source, produces a useful
proposal a human approves, logs everything, and gets better as the artifact history
grows — running safely with a human at the gate, and built from modules clean enough
to extend without a core rewrite.
