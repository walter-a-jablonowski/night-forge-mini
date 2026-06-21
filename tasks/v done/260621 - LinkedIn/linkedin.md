
- The closed-loop self-improving system (the engine) — capture → analyze → propose → improve, artifact-rich, gets better over time
- A whole-company model — loops everywhere, queryable org, software factories, token-maxing, new org archetypes, no middle management

Details

- Closed loop vs open loop — monitor output, adjust to a stated goal. ✅ (loop steps 1–6)
- Every action → an artifact the AI learns from — the append-only store is "make it queryable / legible to AI." ✅
- Self-improves over time — next run ingests accumulated history. ✅
- Propose accurate plans — and v1's example domain is literally the video's: engineering sprint planning. ✅
- Humans at the edge — human at the gate, agent does the work. ✅

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
