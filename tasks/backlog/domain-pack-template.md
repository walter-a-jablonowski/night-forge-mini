# Domain Pack + Registry — Specialization Scaffold

**Deferred from v1.** v1 builds a single hardcoded domain directly against the plain
module interfaces (connector `fetch() -> artifacts`, action `{name, risk_level, run}`,
goal+metric as data, analysis as a function). This item is the **packaging + registry**
layer: bundle those parts into a droppable **Domain Pack** that an auto-discovering
registry loads with **zero core changes**. Extract it when a *second* domain appears —
the v1 seams already match the shapes below, so this is repackaging, not a rewrite.

## A pack provides exactly four things
1. **connectors[]** — input modules. Each: `fetch() -> artifacts` + scoped, read-only-by-default credentials from config.
2. **goal + metric** — what "good" means for this domain (used by analysis and, later, drift detection).
3. **analysis strategy** — the prompt/logic that turns artifacts → a proposal.
4. **actions[]** — output modules the agent may propose; each carries a `risk_level` (gate reads it).

## Suggested layout
```
packs/<domain>/
├─ pack.<ext>          # registers the 4 parts with the core registry
├─ connectors/         # one file per source
├─ actions/            # one file per action, each declares risk_level
├─ analysis.<ext>      # prompt / strategy: artifacts -> proposal
└─ goal.<ext>          # goal + metric definition
```

## Registration contract (shape, not language)
```
register_pack(
  name        = "<domain>",
  connectors  = [ ... ],          # implement fetch() -> artifacts
  goal        = { goal, metric },
  analyze     = (context) -> proposal,
  actions     = [ { name, risk_level, run } ... ],
)
```

## Checklist for a new specialization
- [ ] Pick the goal + the single metric that defines success.
- [ ] Add ≥1 connector with least-privilege, read-only creds.
- [ ] Write the analysis strategy (artifacts → proposal).
- [ ] Declare actions with honest `risk_level` (default to propose-only).
- [ ] Register the pack — confirm the core picks it up with no core edits.
- [ ] Run the loop end-to-end; confirm audit log + cost logging populate.

**Effort per new pack:** S–M (no core changes). **Effort to build the registry boundary:** S–M (deferred until the 2nd domain).
