# night_forge_mini — blank core

The reusable, **domain-agnostic** engine of a self-improving closed-loop system:
capture → ingest → analyze → propose → gate → improve, over an append-only artifact
log, with a per-action approval gate. It has **no use case of its own** — you plug in
exactly one **domain pack** and deploy.

## Deploy a system (blank + one pack)
1. **Duplicate this `blank/` folder** → e.g. `my-system/`.
2. **Copy the contents of a domain** (e.g. `domains/kb/`) into `my-system/`. This drops a
   `domain_pack/` package next to `night_forge_mini/`, plus that domain's `config.json`,
   demo `data/`, and README.
3. `cp .env.example .env` and fill in the provider key for the model you use.
4. Run:
   ```
   python -m night_forge_mini                   # interactive REPL (no command); also `shell`
   python -m night_forge_mini run-once          # one loop pass
   python -m night_forge_mini inbox             # pending actions awaiting approval
   python -m night_forge_mini approve <id>      # approve a held action
   python -m night_forge_mini reject  <id>      # reject a held action
   python -m night_forge_mini trace   <run_id>  # dump a run as a tree
   ```
   Add `--fake-llm` to run the whole loop offline (no API key / no tokens). In the REPL,
   `approve`/`reject` also accept an inbox number (e.g. `approve 1`).

Without a `domain_pack/` present, the core refuses to run and tells you to drop a pack in.

## What's core vs. pack
- **Core (this package):** loop runner, append-only JSONL store (the audit log + source of
  truth), approval gate (reversible hard floor), record schema, the thin model wrapper, and
  the `pack.py` seam.
- **Pack (`domain_pack/`):** the connector(s), the goal, the analysis strategy (which also
  measures the domain's metric), and the actions (each with honest `risk_level`/`reversible`).

## Writing a new domain pack
Provide a `domain_pack` package exposing `build_pack(cfg) -> Pack`. A `Pack` carries the
"four things": `connector`, `goal`, `actions` (name → `Action`), and `analyze`. See
`night_forge_mini/pack.py` for the interfaces and `domains/kb/` for a worked example.

## Config ownership
- `config.json` (deploy root) = operator settings: `provider`/`providers`, `paths`,
  connector params/creds, the **`allow_list`** (which actions may auto-run here), `recent_runs`.
- The pack code owns the domain definition (goal, metric, connector impl, actions). The pack
  declares each action's honest reversibility; your `allow_list` decides what auto-runs.
