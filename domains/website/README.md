# Domain pack: website (self-improving site)

A website under `data/site/` is the materialized artifact; each loop pass captures
external content and improves the site toward the **goal you set in `config.json`**
(`site_goal` + optional brand `constraints`) — the pack is the mechanism, the operator
supplies the objective. Phases 1–2 of `tasks/backlog/website-domain-pack.md`
(phase 3, scheduled `search` mode, is deferred).

## What it does
- **Connector** `web-source` — `pages` mode: a fixed URL list from config, read via the
  core `read_url` tool (Jina Reader → markdown). Snippet id = `url#hash`, so a changed
  page re-ingests and an unchanged one is skipped. A run without new input is a noop.
- **Goal** — from config (`site_goal`), NOT pack code.
- **Agentic analyze** — the model sees the bounded site map and reads on demand:
  `read_page` (site file), `read_url` (external page), `web_search` (research; needs
  `TAVILY_API_KEY` or `EXA_API_KEY`, disables gracefully without one) and `image_search`
  (openly-licensed imagery via Openverse; keyless).
- **Metrics** — pluggable modules under `domain_pack/metrics/`, activated in config:
  `pages`, `broken_links`, `seo_basics` (code) and `goal_coverage` (LLM-as-judge).
  Custom metric = drop `metrics/<name>.py` (exposing `KEYS` + `measure(site, *, model,
  goal)`) into the installation and add its name to config.

### Actions

| action | writes | reversible | gate |
|---|---|---|---|
| `create_page` | a new page/file (refuses to overwrite) | true | auto-runs |
| `add_asset` | downloads an image into `assets/` (create-only) | true | auto-runs |
| `edit_content` | replaces a page's source | **false** | needs git |
| `change_design` | writes a stylesheet (new or existing) | **false** | needs git |
| `remove_page` | deletes a page (never `index.html`) | **false** | needs git |

**Git-backed autonomy:** with git enabled + `per_action` + a clean repo, the gate
auto-runs the irreversible three because every change is `git revert`-able; without
healthy git they safely hold for approval. Drop an action from `allow_list` to hold it
regardless; `allow_list: []` holds everything.

### Constraints — two layers
- **soft** — `constraints` (string or list) is rendered into every prompt. Taste,
  wording, anything unmechanical.
- **hard** — `hard_constraints` is checked *inside* the write actions, so a violation
  fails with `status: error`, writes nothing, and comes back to the model next run via
  `history["failures"]`:
  - `forbidden_colors` — refused in any stylesheet, whichever action writes it, and in
    a page's `<style>` blocks and `style=""` attributes (opt-in),
  - `required_snippets` — must survive an edit of a page that already had them (opt-in),
  - `allow_hotlinking` — **default false**: `<img src="http…">` is refused, so images
    must be downloaded with `add_asset`.

### Images
`add_asset` will not copy an arbitrary web image. A download is permitted only when the
host is in `assets.allowed_hosts` (operator-approved) **or** the payload carries an open
license — `by`, `by-sa`, `cc0`, `pdm` — as returned by `image_search`. The attribution is
written next to the file as `<name>.license.txt`, so provenance is versioned with it.

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
- `domain_pack/constraints.py` — `HardConstraints`: the brand/CI rules refused inside the writes.
- `domain_pack/assets.py` — `AssetPolicy`: the `add_asset` licensing ladder + attribution sidecar.
- `domain_pack/connector.py` — `WebSourceConnector` (`pages` mode).
- `domain_pack/actions.py` — action metadata + `build_actions`.
- `domain_pack/analyze.py` — agentic analysis strategy + prompt + fake mode.
- `domain_pack/metrics/` — metric modules + loader (`__init__.py` documents the interface).
- `config.json` — ready-to-run deploy config (goal = the nutrition test scenario).
- `tests/` — pack tests; run `python -m pytest domains/website/tests` from the repo root
  (no merged installation needed).
