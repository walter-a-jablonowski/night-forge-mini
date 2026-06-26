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
- **actions** with honest `risk_level` / `reversible` (the gate's hard floor decides auto-run):
  | action | reversible | gate behavior |
  |---|---|---|
  | `create_page` (create-only, refuses to overwrite) | true | allow-listable -> auto-run |
  | `edit_content` (overwrites a page body) | **false** | always held for approval |
  | `change_layout` / `change_design` (templates/CSS) | **false** | always held for approval |
  | `remove_page` (deletes a file) | **false** | always held for approval |

  Same honesty rule as the KB pack: the only auto-runnable action is **create-only**; anything
  that overwrites or deletes curated output is `reversible: false` and held.
- **Materialized artifact** = the site files under `data/site/`. The JSONL log stays the
  source of truth; **git** versions `data/site/` and can push to a hosting remote.

## Seed
- A minimal dummy site under `data/site/` (one or two pages + a basic template/CSS) so the
  first run has something to improve.

## Open questions
- **Web fetching deps:** which fetcher (stdlib `urllib` vs `requests` vs a search API)? Search
  needs an API key (config + `.env`), like the LLM providers.
- **Site shape:** static HTML/templates vs a generator (e.g. Eleventy/Hugo)? Start static to
  keep the pack self-contained and the diffs readable.
- **Design changes safely:** how to bound "change layout/design" so a held edit is reviewable
  (diff in the approval UI) rather than a wholesale rewrite.
- **Content-change re-fetch:** detect when a configured page changed (hash) to re-ingest.
- **Goal/metric:** how the LLM measures "improvement" against a free-text config goal
  (LLM-as-judge score vs concrete checks like link/coverage counts).

## Depends on / pairs with
- **git integration** (DONE) — versioning + push of `data/site/`.
- **bounded-retrieval** (DONE) — bound the site context fed to the model, like the KB.
- **approval-ui** / **stale-edit-guard** — diffs + lost-update protection matter more here
  (overwrite + delete are the common case, not the exception).

**Effort:** L — new web connector (+ optional search-API key), several file-shaped actions
including destructive ones, a seed site, and a config-driven goal. Could phase: (1) `pages`
connector + `create_page`/`edit_content` on static HTML; (2) layout/design + `remove_page`;
(3) web `search` mode.
