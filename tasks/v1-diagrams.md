# v1 — Visual Reference

Compact ASCII views of [idea_2.md](idea_2.md). Diagrams only; idea_2 is the source of truth.

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

## 5. Architecture — fixed core + swappable seams (registry deferred)
```
                         ┌─────────── FIXED CORE ───────────┐
   config                │  loop runner                     │
   ├─ goal + metric ────▶│  approval gate (allow-list+rev)  │
   ├─ allow-list ───────▶│  artifact store  (= audit log)   │
   └─ creds ────────────▶│  decide(action_id,verdict,edits) │
                         └───┬───────────┬───────────┬──────┘
        swappable seams →    │           │           │
                   connector │   analysis fn │   action[]        model wrapper
                fetch()->art │  ctx→proposal │  {risk,rev,run}   (1 call site)
                      │             │              │                  │
                 [later: more  [later: per-   [later: autonomy   [later: Langfuse/
                  connectors,   domain         policy+rollback]   LangSmith, OTel]
                  registry]     strategies]
```

## 6. v1 vs the vision (what's in, what's seamed for later)
```
   IN v1  ████████████████  closed loop · artifact store · 1 connector ·
                            sprint-planning domain · gate · scoped autonomy
   LATER  ░░░░░░░░░░░░░░░░  +connectors/multi-channel · dashboards ·
                            software factory · registry/multi-domain ·
                            RBAC · cost/ROI · observability · approval UI
```
