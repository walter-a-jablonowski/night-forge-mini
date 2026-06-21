# Domain Pack — Specialization Scaffold  ✅ RESOLVED (packaging) · registry out of scope

**Status:** the *packaging* half of this item is **implemented**. The system is now a blank,
domain-agnostic core (`blank/night_forge_mini/`) plus one droppable **domain pack**
(`domains/<domain>/domain_pack/`). Adding a domain needs **zero core changes**.

The *registry* half (an auto-discovering loader for many packs in one running app) is
**intentionally not built** — the deployment model is **one pack per deployment**: duplicate
`blank/`, drop in a `domain_pack/`, run. Registration is a single fixed `import domain_pack`
+ `build_pack(cfg) -> Pack`, so no registry is needed. A multi-pack registry would only
return if several domains must run co-resident in one process — not the current model.

## What a pack provides (the "four things") — and where it lives now
1. **connector** — `fetch(seen_ids) -> artifacts` + params/creds from config.
   → `domain_pack/connector.py` (KB: `text-folder`). *(single connector today; a list is a trivial extension)*
2. **goal + metric** — goal on the `Pack`; the metric is measured inside `analyze` and recorded each run.
   → `domain_pack/__init__.py` (goal) + `domain_pack/analyze.py` (metric).
3. **analysis strategy** — artifacts → `{finding, metric, actions}`.
   → `domain_pack/analyze.py`.
4. **actions** — each carries honest `risk_level` **and** `reversible` (gate reads both); `run(target, payload)`.
   → `domain_pack/actions.py` + `build_actions()`.

The interfaces live in core `night_forge_mini/pack.py` (`Connector` / `Action` / `Pack`).

## Registration contract (implemented)
```
# domain_pack/__init__.py
def build_pack(cfg) -> Pack:
    return Pack(domain, goal, connector, actions, analyze)
```
The core does `import domain_pack; pack = domain_pack.build_pack(cfg)`. No global registry —
the pack object is handed straight to the Engine.

## Checklist for a NEW specialization (still the how-to guide)
- [ ] Pick the goal + the single metric that defines success (metric measured in `analyze`).
- [ ] Add a connector with least-privilege, read-only creds (params from `config.json`).
- [ ] Write the analysis strategy (artifacts → `{finding, metric, actions}`).
- [ ] Declare actions with honest `risk_level` + `reversible` (default to propose-only / non-reversible).
- [ ] Implement `build_pack(cfg) -> Pack`; confirm the core runs it with no core edits.
- [ ] Run the loop end-to-end; confirm the audit log populates. *(cost logging is still deferred — see `roi-measurement.md`.)*

**Effort per new pack:** S–M (no core changes). **Registry boundary:** not needed for the
one-pack-per-deploy model; would be S–M only if multi-pack-in-one-process is ever wanted.

See `blank/README.md`, `domains/kb/README.md`, and `tasks/resources/v1-blank-sys-and-domain-pack.md`.
