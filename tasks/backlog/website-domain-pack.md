# Domain pack: website (self-improving homepage)

**Target version: 0.3.0.** Build directly against the post-review core contract (0.2.x):
`analyze(model, *, goal, snippets, history)`, core-side action sanitization, native
structured output (`proposal_schema`), agentic analyze (`run_tools`), `expected_impact`.
The kb pack shows every pattern; see "2026-07-05 contract updates" notes inline below.

**What:** A second domain pack (a `domains/website/` deploy, sibling to `domains/kb/`) whose
materialized artifact is a **website**. It starts as a minimal dummy site, then on each loop
pass consumes content **from the internet** — either via web search or a configured list of
pages — and uses the LLM to **improve the site** toward a goal. It may:
- **Edit content** of existing pages,
- **Change layout / design** (templates, CSS, structure, shared components/fragments),
- **Create or remove sub-pages**,
- **Add images / assets** (see "Images & assets" below — licensing decides the source),
- **Improve SEO** — titles, meta descriptions, sitemap.xml/robots.txt, structured data.
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

## How it maps to the existing architecture
- **One pack per deploy.** The core takes a single `domain_pack`; this is a separate
  deployment (`domains/website/`), not a second pack inside the KB deploy. (Multi-pack in one
  app is still deferred — see the registry note in the main README.)
- **Connector** `web-source` — `fetch(seen_ids) -> artifacts`, returning fetched page text as
  snippets. Two modes via config: `search` (query the web) or `pages` (a fixed URL list).
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
  the CORE sanitizes the returned actions — no pack-side `_normalize`. Measures a pack-owned
  metric (e.g. `pages`, `goal_coverage` (LLM-judged), `broken_links`, `seo_basics` = pages
  with title + meta description — a concrete, cheaply measured SEO floor) and prompts for
  `expected_impact` on those keys, so `history["impact"]` calibrates the pack from run 3 on.
- **actions** with honest `risk_level` / `reversible`. Default gate behavior below assumes
  this pack's **autonomous default** (git-backed; see "Default mode"). The actions stay
  honestly `reversible: false`; git-recoverable is what lets them auto-run:
  | action | reversible | gate behavior (autonomous default) |
  |---|---|---|
  | `create_page` (create-only, refuses to overwrite) | true | auto-run (reversible) |
  | `add_asset` (download image/file into `data/site/assets/`, create-only) | true | auto-run (reversible) |
  | `edit_content` (overwrites a page body) | **false** | auto-run via git-recoverable |
  | `change_layout` / `change_design` (templates/CSS) | **false** | auto-run via git-recoverable |
  | `remove_page` (deletes a file) | **false** | auto-run via git-recoverable |

  Unlike the KB pack (which holds everything destructive), here git makes overwrite/delete
  recoverable, so they auto-run by default. Drop an action from the `allow_list` (or set
  `supervised: true`) to hold it for human approval instead. If git isn't healthy
  (disabled / not `per_action` / dirty repo), the destructive actions **hold** rather than
  risk irreversible loss.
- **Materialized artifact** = the site files under `data/site/`. The JSONL log stays the
  source of truth; **git** versions `data/site/` and can push to a hosting remote.

## Seed
- A minimal dummy site under `data/site/` (one or two pages + a basic template/CSS) so the
  first run has something to improve.

## Images & assets (added 2026-07-06)
`add_asset(target=assets/<name>, payload={url})` downloads an image/file into the site.
Create-only (refuses overwrite) → honestly `reversible: true`, auto-runnable like
`create_page`. Needs a **binary-safe download**: core `fetch_url` decodes text, so this is
either a `fetch_binary` variant (core tool, same scheme/size rules) or a pack-local helper.
**Licensing decides the source** — a generic web image is NOT safe to copy. Preference order:
1. **operator-provided** assets/URLs from config (logo, brand imagery) — always safe,
2. **openly-licensed search** — Openverse / Wikimedia Commons APIs are keyless and return
   license metadata; record attribution in the asset's sidecar or a credits page,
3. **hotlinking** external images — last resort (flaky, someone else's bandwidth), behind a
   config switch, default off.
Image **generation** (keyed image-model API as another core tool) is a possible later add —
it sidesteps licensing entirely but costs money per image.

## Open questions
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
- **Site shape:** static HTML/templates vs a generator (e.g. Eleventy/Hugo)? Start static to
  keep the pack self-contained and the diffs readable.
- **Design changes safely:** how to bound "change layout/design" so a held edit is reviewable
  (diff in the approval UI) rather than a wholesale rewrite.
- **Content-change re-fetch:** ~~TBD~~ resolved by `read_url`: hash the returned markdown,
  snippet id = `url#hash` — a changed page gets a new id and re-ingests via the normal
  watermark, no special mechanism.
- **Goal/metric:** how the LLM measures "improvement" against a free-text config goal
  (LLM-as-judge score vs concrete checks like link/coverage counts).

## Default mode: self-developing site (git-backed autonomy)
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
destructive actions (`edit_content`, `change_layout`, `remove_page`) in the `allow_list`.
Nothing auto-runs that isn't allow-listed (default-deny holds); git is what makes those
destructive actions safe to allow-list.

**Opting back into human approval** (when wanted):
- per action — drop it from the `allow_list` (existing mechanism → that action holds), or
- globally — a `supervised: true` switch that forces every action to hold regardless.

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
- **autonomous-actions** — git-backed autonomy (above) is its first concrete instance; git is
  the rollback substrate that item requires.
- **git integration** (DONE) — versioning + push of `data/site/`.
- **bounded-retrieval** (DONE) — only the site **map** needs bounding now; since
  agentic-analyze (2026-07-05) the model reads full pages on demand via `read_page`
  instead of receiving a pre-sliced context.
- **approval-ui** / **stale-edit-guard** — diffs + lost-update protection matter more here
  (overwrite + delete are the common case, not the exception).

**Effort:** L — new web connector (+ optional search-API key), several file-shaped actions
including destructive ones, a seed site, and a config-driven goal. Phasing:
- **(0) core: git-recoverable floor — DONE.** The gate's hard floor is now
  `reversible OR git_recoverable` (`gate.can_auto_run`), with `Git.recoverable()`
  (enabled + `per_action` + repo healthy + clean) re-checked per action, so a dirty repo /
  failed commit makes destructive actions safely hold. Shipped early via the **KB pack**,
  which is now its first consumer (`edit_entry` allow-listed + git on) — so the website pack
  inherits this for free and starts at (1).
- (1) `pages` connector (via `read_url`) + `create_page`/`edit_content` on static HTML.
  **Model-driven search is already in this phase for free:** hand `web_search` + `read_url`
  into `run_tools` from day one — the model can research during analyze with zero
  connector work. SEO basics ride along too (titles/meta = ordinary content edits;
  `seo_basics` metric key).
- (2) layout/design + `remove_page` + `add_asset` (images; binary download + the
  licensing-source ladder above).
- (3) connector `search` mode — *scheduled* searches producing input snippets (fixed
  queries from config). Possibly unnecessary: build it only if model-driven search from
  (1) proves insufficient for discovering new content.
