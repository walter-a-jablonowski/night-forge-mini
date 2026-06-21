# v1 — Visual Reference

Compact ASCII views of [idea_2.md](<../v done/260621 - idea_2.md>). Diagrams only; idea_2 is the source of truth.

## 1. The closed loop
```
        ┌───────────────────────────────────────────────────┐
        │                                                     │
        ▼                                                     │
   ① CAPTURE ──▶ ② INGEST ──▶ ③ ANALYZE ──▶ ④ PROPOSE ──▶ ⑤ GATE
   connector     recent N      metric vs.    actions[]      allow-list
   → artifacts   runs + slice  goal          +risk+rev      + reversible
        │            │             │              │            │
        └────────────┴─────────────┴──────────────┴────────────┘
                     all steps append to the ARTIFACT STORE
                                                              │
   ⑥ IMPROVE  = next run's INGEST reads this history ◀────────┘
```

## 2. The gate (per action — the only real guardrail)
```
            proposed action {risk_level, reversible}
                          │
                  reversible == true ? ──no──▶ HOLD (human sign-off)
                          │yes
                  in allow-list ?     ──no──▶ HOLD (human sign-off)
                          │yes
                       AUTO-RUN
                          │
   ┌──────────────────────┴───────────────────────┐
   ▼                                               ▼
 AUTO-RUN path                            HOLD path (async)
 decision(auto-run)                       write `pending` action, loop STOPS
 → run() → outcome                        … later, human:
                                            approve → decision → run() → outcome
                                            reject  → decision (no run, no outcome)
        default-deny: anything not matched → HOLD
```

## 3. One run = a trace, reconstructed by `run_id`  (flat log, queried as a tree)
```
run_id = r42                                   ← group by run_id
├─ input      (Capture)   source cursor, fetched artifacts
├─ analysis   (Analyze)   finding + measured metric value
├─ proposal   (Propose)   actions[ x1(low,rev) , x2(high,!rev) ]
│   ├─ x1 ─ decision(auto-run) ─ outcome(ok)         parent_id → x1
│   └─ x2 ─ decision(approved by walter) ─ outcome(ok)   parent_id → x2
└─ …
   record shape: { id, run_id, parent_id?, domain, type,
                   ts, start_ts?, end_ts?, source?, payload, schema_v }
```

## 4. Invocations over time (async approval keeps one run_id)
```
  run-once ─────────────▶ r42: input→analysis→proposal
                          x1 auto-runs ✓        x2 → pending ⏸
                                                     │
  (human reviews inbox)                              │
  approve x2 ───────────▶ r42: +decision +outcome ◀──┘   (resumes r42,
                                                          no new run_id)

  run-once ─────────────▶ r43: input→analysis→… (fresh run_id)
```

## 5. Architecture — blank core + one pluggable domain pack
```
   config.json (deploy)         ┌──────────── BLANK CORE ────────────┐
   ├─ provider / model ────────▶│  loop runner                       │
   ├─ allow-list ─────────────▶│  approval gate (allow-list + rev)  │
   ├─ paths ──────────────────▶│  artifact store (= audit log)      │
   └─ connector source/creds ─▶│  decide(action_id, verdict, edits) │
                                │  model wrapper (1 call site)       │
                                │  pack seam: Connector/Action/Pack  │
                                └─────────────────┬──────────────────┘
                                                  │ build_pack(cfg) -> Pack
            ┌───────────────── DOMAIN PACK (domain_pack/) ─────────────────┐
            │  goal                                                        │
            │  connector    fetch() -> artifacts                           │
            │  analysis fn  ctx -> proposal   (also measures the metric)   │
            │  actions[]    { name, risk, reversible, run }                │
            └──────────────────────────────────────────────────────────────┘
     deploy = duplicate blank/ + drop in one domain_pack/   (no registry)
```

## 6. Now vs the vision (what's in, what's seamed for later)
```
   IN     ████████████████  closed loop · artifact store · blank core +
                            pluggable domain pack (KB demo) · gate ·
                            scoped autonomy · 1 connector
   LATER  ░░░░░░░░░░░░░░░░  bounded retrieval · observability · cost/ROI ·
                            approval UI · RBAC · autonomy policy · drift ·
                            multi-channel · dashboards · software factory ·
                            multi-loop registry (1 pack/deploy already done)
```
