# night-forge-mini — agent guide

## Layout

```
blank/            the core. No domain knowledge. SOURCE OF TRUTH for core code.
  night_forge_mini/
  tests/
domains/<x>/      one domain pack: connector, goal, analyze, actions, metrics
  domain_pack/    + config.json + data/ (seed) + tests/
try/<x>/          a MERGED deploy (see below). Scratch, gitignored.
tasks/            worklist + backlog (see below)
```

## Deploy model — read before running anything

```
  blank/night_forge_mini/  ─┐
                            ├─► try/website/   (a copy of BOTH, side by side)
  domains/website/*        ─┘
```

- An installation = core + **one** pack, **copied** together. Not a symlink, not a package.
- A deploy does **not** auto-update. Edit the sources, never the copy.
- After any core/pack change, re-sync before running the deploy:

```
cp -r blank/night_forge_mini/. try/website/night_forge_mini/
cp -r domains/website/domain_pack/. try/website/domain_pack/
```

- **Keep `try/*/config.json`** — it holds deploy-local choices (backend, model, timeouts).
- Verify: `diff -rq blank/night_forge_mini try/website/night_forge_mini -x __pycache__`

## Commands

| what | command |
|---|---|
| tests | `python -m pytest blank/tests domains/website/tests -q` |
| one pass | `python -m night_forge_mini run-once` (from a deploy dir) |
| offline pass | `python -m night_forge_mini --fake-llm run-once` |
| held actions | `inbox` · `approve <id>` · `reject <id>` · `trace <run_id>` |

## Key seams

| seam | file | note |
|---|---|---|
| `Pack` | `blank/night_forge_mini/pack.py` | what a domain must provide |
| `Backend` | `blank/night_forge_mini/backends/base.py` | http · fake · claudeCode |
| `Tool` | `blank/night_forge_mini/tools/registry.py` | also served over MCP |
| gate | `blank/night_forge_mini/gate.py` | allow-list + reversible/git hard floor |

## How `/tasks` works

| path | edited by | what |
|---|---|---|
| `-this.md` | **human only** | active worklist — agent edits only when asked |
| `dev_info.md` | **human only** | dev notes — same rule |
| `backlog.md` | agent | version → task list, priority-ordered |
| `backlog/` | agent | one file per task (user may add too) |
| `v done/` | agent | finished, `YYMMDD - name.md` |
| `resources/` | either | linked long-term reference, no tasks |
| `overview/` | agent **on request** | system overview |
| `README.md` | either | how-to-use information |

Rules

- one task = one file in `backlog/`; update `backlog.md` in the **same** change
- done → `git mv` into `v done/` with a `YYMMDD - ` prefix
- leftovers of a finished task → a **new** `backlog/` file; never leave them in the archive
- moving a file breaks links → re-check `backlog.md` and `-this.md` afterwards
- before adding a task, grep `backlog/` — duplicates hide under different names

## Output style

- short nested outlining, tables, ascii diagrams
- limit prose
- say what was verified vs assumed; name the check that was run
