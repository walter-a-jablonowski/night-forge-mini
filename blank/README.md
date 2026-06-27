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

## Tools (shared toolbox)
The core ships a small tool registry (`night_forge_mini/tools/`) so packs don't reimplement
common infra. Built-ins are stdlib-only (zero extra dependency):
- `fetch_url(url)` — HTTP(S) GET → text (refuses non-http(s); size-capped).
- `html_to_text(html)` — strip HTML to readable plain text.

Use one from a pack:
```python
from night_forge_mini.tools import registry
text = registry.get("fetch_url").run("https://example.com")
```
A pack registers its own (keyed / heavier) tools inside `build_pack(cfg)` via
`registry.register(Tool(...))`. A tool needing a secret names the **env-var** in `requires`
(the key lives in `.env`, like the model providers); `tool.available()` is `False` when it's
missing, so the capability disables gracefully instead of crashing. File layout: a simple
tool is one file `tools/MY_TOOL.py`; a complex tool is its own package `tools/MY_TOOL/`.

## Config ownership
- `config.json` (deploy root) = operator settings: `provider`/`providers`, `paths`,
  connector params/creds, the **`allow_list`** (which actions may auto-run here), `recent_runs`.
- The pack code owns the domain definition (goal, metric, connector impl, actions). The pack
  declares each action's honest reversibility; your `allow_list` decides what auto-runs.

## Optional: git versioning of the materialized artifacts
The JSONL log is always the source of truth. On top of it you can **optionally** version the
files a pack writes (the KB markdown, a website's pages, …) in git, getting real diffs and
`git revert`. This is the **command-line variant**: the core shells out to your installed
`git`, reusing your existing auth (SSH key / credential helper / token) — the app stores no
credentials.

Enable it in `config.json`:
```json
"git": { "enabled": true, "repo_dir": "data", "granularity": "per_run", "remote": "", "branch": "main" }
```
- `granularity`: `per_run` (one commit per loop pass, default) or `per_action` (one per action).
- `remote`: leave empty for **local-only**; set it (e.g. `origin`) to also **push** after each
  commit. A push failure never breaks the loop — the local commit is kept and a warning printed.
- A single approved/held action always commits on success, regardless of `granularity`.

**Requirement — pre-initialize the repo yourself.** The core commits/pushes but never runs
`git init`. Before enabling, create the artifact repo:
```
cd <deploy>/data        # = your repo_dir
git init
git remote add origin <url>   # only if you set "remote": "origin"
```
`repo_dir` **must be the root of its own repo** and **must not be the project's source repo** —
the core refuses to commit if `repo_dir` is merely *inside* another repo (so it can never touch
the source `.git/`). `git` must be on `PATH`; if it isn't, versioning is silently skipped.
