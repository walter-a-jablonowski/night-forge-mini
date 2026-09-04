# Domain pack: website (self-improving homepage)

## Status (checked 2026-09-04)

**Phases 0 + 1 + 2 are SHIPPED — the pack is implemented, not new work.** Everything below
marked ✅ / DONE is in the repo: `domains/website/` (connector, analyze, 5 actions, 4 metric
modules, seed site, hard constraints, asset licensing) plus the core tool `image_search` in
`blank/night_forge_mini/tools/`. Merged deploy in `try/website/`.
96 tests pass: `python -m pytest domains/website/tests blank/tests`.

**Still open:**
- **(3) connector `search` mode** — the only unbuilt phase, and explicitly build-only-if-needed:
  model-driven `web_search` during analyze already covers discovery. Caution: scheduled
  searches make input effectively infinite, so the `seen_ids` watermark stops bounding runs
  and only the gate does — a goal-reached / convergence stop condition should land first.
- **Real-model end-to-end run** — so far only `--fake-llm` (with live Jina capture, live
  Openverse search, a real image download and per-action git commits). `try/website/` is a
  ready merged deploy and needs `OPENROUTER_API_KEY`.
- **Owned by other tasks, not by this one** — `approval-ui` (diff of a *held* proposal before
  it is applied), `autonomous-actions` (the general, risk-classifier version), observability
  and cost logging (agentic analyze multiplies model calls per run).

---

**Target version: 0.3.0.** Build directly against the post-review core contract (0.2.x):
`analyze(model, *, goal, snippets, history)`, core-side action sanitization, native
structured output (`proposal_schema`), agentic analyze (`run_tools`), `expected_impact`.
The kb pack shows every pattern; see "2026-07-05 contract updates" notes inline below.

**What:** A second domain pack (a `domains/website/` deploy, sibling to `domains/kb/`) whose
materialized artifact is a **website**. It starts as a minimal dummy site, then on each loop
pass consumes content **from the internet** — either via web search or a configured list of
pages — and uses the LLM to **improve the site** toward a goal. It may *(all five ✅ shipped)*:
- ✅ **Edit content** of existing pages,
- ✅ **Change layout / design** (CSS; see phase 2 — `change_layout` was dropped as redundant
  with `edit_content`, `change_design` is the CSS-scoped action),
- ✅ **Create or remove sub-pages**,
- ✅ **Add images / assets** (see "Images & assets" below — licensing decides the source),
- ✅ **Improve SEO** — titles, meta descriptions, sitemap.xml/robots.txt, structured data.
  No new machinery: these are ordinary `edit_content`/`create_page` writes; make SEO an
  explicit improvement dimension in the prompt and a metric key (see metric below).

The **goal and the "how to improve" instructions are supplied by the user in `config.json`**
(not hard-coded in the pack, unlike the KB pack whose goal is a constant). Config also carries
**brand / CI constraints** the LLM must respect (e.g. logos, color palette, fixed elements) —
"must-have" content and design invariants that improvements may not violate.
Enforcement is two-layered: (soft) the constraints block is rendered into the system
prompt on EVERY run; (hard, optional) actions can refuse violating writes — e.g.
`change_design` rejects CSS containing forbidden colors, `edit_content` refuses to drop
a required logo/element — the same refuse-inside-the-action pattern as the KB's
create-only `add_entry`.

**Why:** It exercises the core on a genuinely **destructive, file-shaped** domain (overwrite
+ delete), which is exactly why git versioning was just added. It's also a compelling demo of
the closed loop producing a tangible, deployable artifact.

**Value:**
- Proves the pack seam generalizes beyond the additive KB to overwrite/delete domains.
- Pairs naturally with the shipped git integration: every site change is committed (and
  optionally pushed to a host) — real diffs + `git revert` for layout/content/page changes.
- Config-driven goal shows the goal can be operator data, not just pack code.

## How it maps to the existing architecture — ✅ implemented
- **One pack per deploy.** The core takes a single `domain_pack`; this is a separate
  deployment (`domains/website/`), not a second pack inside the KB deploy. (Multi-pack in one
  app is still deferred — see the registry note in the main README.)
- **Connector** `web-source` — `fetch(seen_ids) -> artifacts`, returning fetched page text as
  snippets. Two modes via config: `search` (query the web) or `pages` (a fixed URL list).
  ✅ `pages` mode is shipped; ⚠️ `search` mode is phase 3 and NOT built — an unknown mode
  raises in `domain_pack/__init__.py`.
  `pages` mode fetches via the core **`read_url`** (Jina Reader → clean markdown snippets,
  much better model input than raw HTML; `fetch_url`+`html_to_text` as fallback when Jina
  is unreachable). Dedup via the same `seen_ids` watermark; re-fetch = hash of the returned
  markdown (snippet id = `url#hash`, so a changed page re-ingests).
  **Capture vs. read split:** the connector is scheduled *capture* — what's new becomes
  logged `input` records and drives the watermark; the agentic tools below are on-demand
  *reads* during analysis — context, logged as `tool_call` spans, never inputs. Same
  underlying tools, different roles in the loop.
- **Goal from config** — `build_pack(cfg)` reads `cfg.get("site_goal")` / improvement
  instructions and passes them as the pack's `goal`. (Today `Pack.goal` is a constant; this
  pack makes it config-sourced — no core change, just how the pack builds itself.)
- **analyze** *(updated 2026-07-05 to the new contract)* — signature
  `(model, *, goal, snippets, history)`; `history` brings findings, metric trend, human
  rejections, failed actions and predicted-vs-actual impact for free — render them into the
  prompt like the KB pack does. Use the **agentic loop** (`model.run_tools`, budget via an
  `analyze_tool_steps` config key like the KB's): give the model the site **map** (bounded
  page list) plus READ-ONLY tools — a pack `read_page(path)` (full source of one page, the
  `read_entry` analogue) and the core `read_url` (Jina Reader, clean markdown — the default
  for external pages), `web_search`, `fetch_url`/`html_to_text` (raw sources; all
  model-exposable, they carry `params` schemas) — so it reads pages/sources on demand instead of stuffing a
  "bounded slice of pages" into context. Proposal via `proposal_schema(<action enum>)`;
  the CORE sanitizes the returned actions — no pack-side `_normalize`. Measures the metrics
  the site config activates (pluggable metric modules — see the resolved Goal/metric question
  below; shipped: `pages`, `goal_coverage` (LLM-judged), `broken_links`, `seo_basics` = pages
  with title + meta description — a concrete, cheaply measured SEO floor) and prompts for
  `expected_impact` on those keys, so `history["impact"]` calibrates the pack from run 3 on.
- **actions** with honest `risk_level` / `reversible`. Default gate behavior below assumes
  this pack's **autonomous default** (git-backed; see "Default mode"). The actions stay
  honestly `reversible: false`; git-recoverable is what lets them auto-run:
  | action | reversible | gate behavior (autonomous default) |
  |---|---|---|
  | ✅ `create_page` (create-only, refuses to overwrite) | true | auto-run (reversible) |
  | ✅ `add_asset` (download image/file into `data/site/assets/`, create-only) | true | auto-run (reversible) |
  | ✅ `edit_content` (overwrites a page body) | **false** | auto-run via git-recoverable |
  | ✅ `change_design` (stylesheets — see phase 2 note: `change_layout` was dropped) | **false** | auto-run via git-recoverable |
  | ✅ `remove_page` (deletes a page; never `index.html`) | **false** | auto-run via git-recoverable |

  Unlike the KB pack (which holds everything destructive), here git makes overwrite/delete
  recoverable, so they auto-run by default. Drop an action from the `allow_list` to hold it
  for human approval instead. If git isn't healthy
  (disabled / not `per_action` / dirty repo), the destructive actions **hold** rather than
  risk irreversible loss.
- **Materialized artifact** = the site files under `data/site/`. The JSONL log stays the
  source of truth; **git** versions `data/site/` and can push to a hosting remote.

## Seed — ✅ shipped
- *(decided 2026-07-11)* A **very basic, mostly blank start page** under `data/site/`
  (one `index.html` + minimal CSS, near-empty content) so the first run has something to
  improve. The app fills / develops it purely from the user's config goal — the seed carries
  **no topic of its own**; topic content comes from `site_goal`, not from the pack.
- **Test scenario (config, not seed): simple healthy nutrition.** `site_goal` for testing:
  - ingredients,
  - simple meals — fast to make (sample: put in a bowl, heat up, ready), good nutrient
    combinations per meal, cheap where possible (price is lower priority).

## Images & assets (added 2026-07-06) — ✅ SHIPPED 2026-07-28
`add_asset(target=assets/<name>, payload={url})` downloads an image/file into the site.
Create-only (refuses overwrite) → honestly `reversible: true`, auto-runnable like
`create_page`. Needs a **binary-safe download**: core `fetch_url` decodes text, so
*(resolved + SHIPPED 2026-07-11)* this is the **core tool `fetch_binary`** in blank's
`tools/` — same scheme refusal as `fetch_url`, but it *raises* on oversize instead of
truncating (a truncated image is silent corruption) and has **no `params` schema** (bytes
are not model-consumable → never exposed via `run_tools`; pack code calls it).
**Licensing decides the source** — a generic web image is NOT safe to copy. Preference order:
1. **operator-provided** assets/URLs from config (logo, brand imagery) — always safe,
2. **openly-licensed search** — Openverse / Wikimedia Commons APIs are keyless and return
   license metadata; record attribution in the asset's sidecar or a credits page,
3. **hotlinking** external images — last resort (flaky, someone else's bandwidth), behind a
   config switch, default off.
Image **generation** (keyed image-model API as another core tool) is a possible later add —
it sidesteps licensing entirely but costs money per image.

## Metric modules — interface (decided 2026-07-11) — ✅ SHIPPED (all four modules)
The pluggable-metrics decision (see Goal/metric below), made concrete. Design goals: fits the
existing contract (metric = the flat `{key: number}` dict `analyze` returns; the core just
records it), follows the tools-registry house style (explicit, no import-time magic), and
makes operator drop-in trivial because an installation = blank + pack merged on disk.

- **Location:** `domain_pack/metrics/<name>.py` — one module per metric.
- **Module contract:** each module exposes two things:
  ```python
  KEYS = ["seo_basics"]                 # metric keys it produces (feeds the expected_impact prompt)

  def measure(site, *, model, goal) -> dict[str, float]:
      ...                               # e.g. {"seo_basics": 7}
  ```
  `site` is the pack's file API over `data/site/` (the `KnowledgeBase` analogue). `model` is
  the LLM wrapper — only judge-style metrics use it; code metrics ignore it. A metric that
  needs a tool (e.g. an SEO check fetching something) calls `registry.get(...)` like any
  pack code — no extra plumbing.
- **Activation via config:** `"metrics": ["pages", "goal_coverage", "broken_links", "seo_basics"]`.
  Resolution: built-ins are wired explicitly in `metrics/__init__.py` (a name → module map,
  like `tools/__init__.py`); an unknown name falls back to
  `importlib.import_module(f"domain_pack.metrics.{name}")` — so a **custom metric = drop
  `my_metric.py` into `metrics/` + add its name to config**, no code edits.
- **analyze integration:** `metric = merge of measure() results across active modules`;
  the `expected_impact` prompt lists the union of active modules' `KEYS`, so the model
  predicts exactly what will be measured.
- **Judge metrics & fake mode:** `goal_coverage` (LLM-as-judge, 0–10 against the free-text
  `site_goal`) costs one model call per run — that's fine, but under `--fake-llm`
  (`model.fake`) every judge metric must return a deterministic constant so the offline
  loop stays reproducible.
- **Failure isolation:** a module that raises is skipped — its keys are omitted from that
  run's metric and the error is noted in the finding/log; a broken metric must never kill
  the run.

Shipped built-ins: `pages` (count), `broken_links` (internal links only), `seo_basics`
(pages with title + meta description), `goal_coverage` (judge).

## Open questions — ✅ all resolved
- **Web fetching deps — resolved → its own task `tool-registry.md` (DONE).** The core has a
  tool registry + `night_forge_mini/tools/` with stdlib built-ins (`fetch_url`,
  `html_to_text`, and since 2026-07-06 **`web_search`** — Tavily/Exa behind one core tool,
  keys via `.env` — and **`read_url`** — Jina Reader → markdown, free tier keyless), landed
  **before** this pack. So **`pages` mode uses the core `read_url`** and **`search` mode
  uses the core `web_search`** — the pack registers no fetch/search tool of its own.
  See `tool-registry.md` for the full design and boundaries.
  *Since 2026-07-05 tools are also model-exposable* (a `params` schema + `run_tools`):
  the search tool can be handed to the MODEL during analyze — it decides what to search —
  not only called by connector code. Every model tool call is logged as a `tool_call` span.
- **Site shape:** ~~TBD~~ **resolved 2026-07-11 — no frameworks, no generators.** Plain
  HTML/JS/CSS; some sites may use PHP (custom development). The pack only reads/writes site
  files as text and never executes the site, so `.php` pages work exactly like `.html` ones —
  only the seed site and the default prompts assume plain HTML.
- **Design changes safely:** ~~TBD~~ **resolved 2026-07-11 — git is the mechanism.** In the
  autonomous default every action is its own commit (`per_action`), so each layout/design
  change has a readable diff and is `git revert`-able — review happens post-hoc via git.
  The one gap git can't cover — a diff of a *held* proposal BEFORE it is applied (payload vs
  current file) — belongs to **approval-ui**, not this pack.
- **Content-change re-fetch:** ~~TBD~~ resolved by `read_url`: hash the returned markdown,
  snippet id = `url#hash` — a changed page gets a new id and re-ingests via the normal
  watermark, no special mechanism.
- **Goal/metric:** ~~TBD~~ **resolved 2026-07-11 — pluggable metric modules, selected in the
  site config.** Two kinds, freely combinable:
  1. **LLM-as-judge** — scores the site against the free-text config goal (`goal_coverage`),
  2. **code metrics** — a piece of code that computes/queries a value, and may call a tool
     (e.g. an SEO check, `broken_links`, `seo_basics`, `pages`).
  The pack ships a set of **ready-to-use metric modules** (the four named above); because an
  installation = blank core merged with the pack on disk, an operator can drop in **custom
  metric modules** next to them without touching core or pack. Config lists which metrics are
  active; `expected_impact` is prompted on exactly those keys.
  **Interface specified 2026-07-11 — see "Metric modules — interface" above.**

## Default mode: self-developing site (git-backed autonomy) — ✅ SHIPPED (it is the deploy config)
**This pack is autonomous by default** — the LLM develops the site on its own, with git as
the undo. Human approval is **optional** (opt-in), not the norm. It needs **no action-shape
change**: the actions stay honestly `reversible: false`. The mechanism is the existing
allow-list plus one **core** change — the gate's *reversible hard floor* also accepts
*git-recoverable* as satisfying reversibility:
```
auto-run when  name in allow_list
               AND ( act.reversible OR git_recoverable )
git_recoverable = git.enabled AND granularity == per_action AND repo clean AND git covers repo_dir
```
So "autonomous by default" is just the **shipped config**: git enabled, `per_action`, and the
destructive actions (`edit_content`, `change_design`, `remove_page`) in the `allow_list`.
Nothing auto-runs that isn't allow-listed (default-deny holds); git is what makes those
destructive actions safe to allow-list.

**Opting back into human approval** (when wanted) — the allow-list already expresses both,
no extra switch (a `supervised: true` flag was considered and dropped 2026-07-11 as
redundant: default-deny + git undo + the JSONL audit log cover it):
- per action — drop it from the `allow_list` (existing mechanism → that action holds),
- globally — `allow_list: []` → every action holds.

Requirements so git is a genuine undo (else fall back to holding, not silent data loss):
- **`granularity: per_action`** so each change is independently `git revert`-able.
- **Refuse** autonomous auto-run unless git is enabled and the repo is clean/committed (the
  per-run commit keeps the last-good state in git by induction).
- A **commit failure stops** the autonomous chain (a *push* failure is fine — local commit is
  the undo point).

This is the first concrete, low-risk instance of **autonomous-actions** (earned autonomy):
git supplies the rollback mechanism that backlog item names as the precondition — no risk
classifier required, because every change is recoverable.

## Depends on / pairs with
- **tool-registry** (DONE) — supplies the core `fetch_url` / `html_to_text` / `web_search`
  tools; both `pages` and `search` mode are batteries-included, no pack tool needed.
- **autonomous-actions** — ✅ git-backed autonomy (above) shipped as its first concrete
  instance; the general risk-classifier version stays OPEN in that task.
- **git integration** (DONE) — versioning + push of `data/site/`.
- **bounded-retrieval** (DONE) — only the site **map** needs bounding now; since
  agentic-analyze (2026-07-05) the model reads full pages on demand via `read_page`
  instead of receiving a pre-sliced context.
- **approval-ui** (OPEN, other task) / **stale-edit-guard** (✅ DONE, wired on `edit_content`)
  — diffs + lost-update protection matter more here (overwrite + delete are the common
  case, not the exception).

**Effort:** L — new web connector (+ optional search-API key), several file-shaped actions
including destructive ones, a seed site, and a config-driven goal. Phasing:
- **(0) core: git-recoverable floor — ✅ DONE.** The gate's hard floor is now
  `reversible OR git_recoverable` (`gate.can_auto_run`), with `Git.recoverable()`
  (enabled + `per_action` + repo healthy + clean) re-checked per action, so a dirty repo /
  failed commit makes destructive actions safely hold. Shipped early via the **KB pack**,
  which is now its first consumer (`edit_entry` allow-listed + git on) — so the website pack
  inherits this for free and starts at (1).
- **(1) — ✅ DONE 2026-07-11** (`domains/website/`): `pages` connector (via `read_url`) +
  `create_page`/`edit_content` on static HTML; `web_search` + `read_url` + `read_page`
  handed into `run_tools`; the four metric modules (incl. `seo_basics`) per the interface
  above; near-blank seed; config-sourced goal/constraints/metrics; stale-edit guard on
  `edit_content`. 21 pack tests (`python -m pytest domains/website/tests`) + a merged-deploy
  smoke run (fake LLM, live Jina fetch, per-action git commit) verified.
- **(2) — ✅ DONE 2026-07-28**: `change_design` (stylesheets), `remove_page`, `add_asset`
  (binary download + licensing ladder), and the HARD half of constraint enforcement.
  Decisions taken while building, all narrowing the spec:
  - **`change_layout` was dropped; `change_design` is CSS-scoped.** The two would have
    shared `edit_content`'s write policy exactly — a layout change to a page *is* an edit
    of that page's HTML. `change_design` earns its separate identity by having a genuinely
    different policy (create-or-overwrite, `.css` only, CSS constraint checks) and by
    giving restyles their own line in the `allow_list`.
  - **`image_search` is a new CORE tool** (`blank/night_forge_mini/tools/image_search.py`)
    — Openverse, keyless, filtered to `license_type=commercial,modification`, returns
    license + creator + source + attribution. It is domain-agnostic, so it sits next to
    `web_search` rather than in the pack, and it is model-exposed during analyze.
  - **`add_asset` enforces the licensing ladder in code** (`domain_pack/assets.py`):
    rung 1 = host in `assets.allowed_hosts`, rung 2 = an open license (`by`, `by-sa`,
    `cc0`, `pdm`) in the payload; anything else is refused before any download happens.
    Attribution is written to a `<name>.license.txt` sidecar, versioned by git with the
    image. Rung 3 (hotlinking) is not a download and is enforced on the page source
    instead — `hard_constraints.allow_hotlinking`, default false.
  - **Hard constraints live in `domain_pack/constraints.py`**, separate from `Site`: the
    Site owns paths and bytes, `HardConstraints` owns what content is acceptable. A
    refusal surfaces as `status: error` → logged as an outcome → back to the model next
    run via `history["failures"]`.
  - **`remove_page` refuses `index.html`** and stylesheets (pages only). Deleting the home
    page is the one loss git-revert-ability does not make cheap enough to risk.
  - `risk_level`: `remove_page` high, `edit_content`/`change_design` medium, the two
    create-only actions low.

  95 tests (`python -m pytest domains/website/tests blank/tests`; 96 as of 2026-09-04)
  + a merged-deploy smoke
  run in `try/website/` verified: live Jina capture, per-action git commit, live Openverse
  search, a real 150 KB image download with its sidecar, and each refusal path.
- **(3) — ⚠️ OPEN, the only unbuilt phase**: connector `search` mode — *scheduled* searches
  producing input snippets (fixed queries from config). Possibly unnecessary: build it only
  if model-driven search from (1) proves insufficient for discovering new content. Note it
  removes the watermark's natural quiescence — see Status at the top.
