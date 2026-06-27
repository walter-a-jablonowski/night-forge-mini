# Domain pack: website (self-improving homepage)

**What:** A second domain pack (a `domains/website/` deploy, sibling to `domains/kb/`) whose
materialized artifact is a **website**. It starts as a minimal dummy site, then on each loop
pass consumes content **from the internet** — either via web search or a configured list of
pages — and uses the LLM to **improve the site** toward a goal. It may:
- **Edit content** of existing pages,
- **Change layout / design** (templates, CSS, structure),
- **Create or remove sub-pages**.

The **goal and the "how to improve" instructions are supplied by the user in `config.json`**
(not hard-coded in the pack, unlike the KB pack whose goal is a constant). Config also carries
**brand / CI constraints** the LLM must respect (e.g. logos, color palette, fixed elements) —
"must-have" content and design invariants that improvements may not violate.

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
  Dedup via the same `seen_ids` watermark; re-fetch policy (content hash) TBD.
- **Goal from config** — `build_pack(cfg)` reads `cfg.get("site_goal")` / improvement
  instructions and passes them as the pack's `goal`. (Today `Pack.goal` is a constant; this
  pack makes it config-sourced — no core change, just how the pack builds itself.)
- **analyze** — feeds the LLM: current site (bounded slice of pages/structure), the freshly
  fetched web content, and the config goal -> `{finding, metric, actions}`. Measures a
  pack-owned metric (e.g. `pages`, `goal_coverage` (LLM-judged), `broken_links`).
- **actions** with honest `risk_level` / `reversible`. Default gate behavior below assumes
  this pack's **autonomous default** (git-backed; see "Default mode"). The actions stay
  honestly `reversible: false`; git-recoverable is what lets them auto-run:
  | action | reversible | gate behavior (autonomous default) |
  |---|---|---|
  | `create_page` (create-only, refuses to overwrite) | true | auto-run (reversible) |
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

## Open questions
- **Web fetching deps — resolved → its own task `tool-registry.md` (do first).** The core gets
  a tool registry + `night_forge_mini/tools/` with stdlib built-ins (`fetch_url`,
  `html_to_text`), landed **before** this pack. So **`pages` mode uses the core fetcher**;
  **`search` mode is a pack-registered tool** (e.g. Exa — needs a key in config + `.env`,
  like the LLM providers). See `tool-registry.md` for the full design and boundaries.
- **Site shape:** static HTML/templates vs a generator (e.g. Eleventy/Hugo)? Start static to
  keep the pack self-contained and the diffs readable.
- **Design changes safely:** how to bound "change layout/design" so a held edit is reviewable
  (diff in the approval UI) rather than a wholesale rewrite.
- **Content-change re-fetch:** detect when a configured page changed (hash) to re-ingest.
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
- **tool-registry** (do first) — supplies the core `fetch_url` / `html_to_text` tools this
  pack's `pages` mode uses; `search` mode registers a pack tool (e.g. Exa) on top.
- **autonomous-actions** — git-backed autonomy (above) is its first concrete instance; git is
  the rollback substrate that item requires.
- **git integration** (DONE) — versioning + push of `data/site/`.
- **bounded-retrieval** (DONE) — bound the site context fed to the model, like the KB.
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
- (1) `pages` connector + `create_page`/`edit_content` on static HTML.
- (2) layout/design + `remove_page`.
- (3) web `search` mode.
