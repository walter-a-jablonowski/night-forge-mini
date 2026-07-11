# Domain pack: website (self-improving site)

A website under `data/site/` is the materialized artifact; each loop pass captures
external content and improves the site toward the **goal you set in `config.json`**
(`site_goal` + optional brand `constraints`) — the pack is the mechanism, the operator
supplies the objective. Phase 1 of `tasks/backlog/website-domain-pack.md`.

## What it does
- **Connector** `web-source` — `pages` mode: a fixed URL list from config, read via the
  core `read_url` tool (Jina Reader → markdown). Snippet id = `url#hash`, so a changed
  page re-ingests and an unchanged one is skipped. A run without new input is a noop.
- **Goal** — from config (`site_goal`), NOT pack code. `constraints` (string or list)
  are rendered into every prompt (soft enforcement in phase 1).
- **Agentic analyze** — the model sees the bounded site map and reads on demand:
  `read_page` (site file), `read_url` (external page), `web_search` (research; needs
  `TAVILY_API_KEY` or `EXA_API_KEY`, disables gracefully without one).
- **Metrics** — pluggable modules under `domain_pack/metrics/`, activated in config:
  `pages`, `broken_links`, `seo_basics` (code) and `goal_coverage` (LLM-as-judge).
  Custom metric = drop `metrics/<name>.py` (exposing `KEYS` + `measure(site, *, model,
  goal)`) into the installation and add its name to config.
- **Actions** — `create_page` (create-only ⇒ reversible) and `edit_content` (overwrites
  ⇒ NOT reversible). **Git-backed autonomy:** with git enabled + `per_action` + a clean
  repo, the gate auto-runs `edit_content` because every change is `git revert`-able;
  without healthy git it safely holds for approval. Phase 2 adds
  `change_layout`/`change_design`, `remove_page`, `add_asset`.

## Seed
`data/site/` ships a near-blank `index.html` + minimal `style.css` — deliberately
empty: all topic content comes from `site_goal`. The shipped config carries the
"simple healthy nutrition" test scenario; replace it with your own goal.

## Deploy
Copy the **contents** of this folder into a duplicate of `blank/`:
```
my-site-system/
├─ night_forge_mini/   (from blank/)
├─ domain_pack/        (from here)
├─ config.json         (from here — set site_goal, constraints, connector pages)
├─ data/site/          (seed, from here)
├─ .env                (cp from .env.example; provider key + optional TAVILY/EXA/JINA keys)
└─ requirements.txt    (from blank/)
```
Then initialize the site's own artifact repo (required for autonomous edit_content):
```
cd data/site && git init && git add -A && git commit -m seed && cd ../..
```
Run:
```
python -m night_forge_mini --fake-llm run-once   # offline demo, no key needed
python -m night_forge_mini run-once              # real model
python -m night_forge_mini inbox                 # held actions (e.g. edits while git is dirty)
python -m night_forge_mini approve <action_id>
python -m night_forge_mini trace <run_id>
```

## Files
- `domain_pack/__init__.py` — `build_pack(cfg) -> Pack` (config-sourced goal/constraints/metrics).
- `domain_pack/site.py` — `Site`: safe file API over `data/site/` (path safety, map, read, writes).
- `domain_pack/connector.py` — `WebSourceConnector` (`pages` mode).
- `domain_pack/actions.py` — action metadata + `build_actions`.
- `domain_pack/analyze.py` — agentic analysis strategy + prompt + fake mode.
- `domain_pack/metrics/` — metric modules + loader (`__init__.py` documents the interface).
- `config.json` — ready-to-run deploy config (goal = the nutrition test scenario).
- `tests/` — pack tests; run `python -m pytest domains/website/tests` from the repo root
  (no merged installation needed).
