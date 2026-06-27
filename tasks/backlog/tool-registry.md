# Core tool registry + built-in tools (`night_forge_mini/tools/`)

**What:** Give the blank core a small **tool registry** plus a `night_forge_mini/tools/`
package of basic, reusable tools. A *tool* is a domain-agnostic capability a pack's
connector / action / analyze can call (e.g. fetch a URL, strip HTML to text). The core
ships a few stdlib-only built-ins; packs may register their own. This lands **before** the
website pack, which then just consumes the registry instead of carrying its own fetcher.

**Why:** Today the core ships **no tools** — only the `Connector` / `Action` / `Pack` seams,
stdlib-only except `openai`. Every pack that needs HTTP would otherwise reimplement it. A
registry keeps fetching DRY, makes the core "batteries-included" for the common case, and
gives a single, honest place to declare a tool's dependencies / required keys and degrade
gracefully when they're missing (same spirit as `Git.available()`).

## Design
- **Package** `night_forge_mini/tools/` with the registry + built-ins. Mirrors the existing
  dataclass-seam style (`Pack`, `Action`) — no framework.
- **`Tool` dataclass:** `name`, `description`, `run(**kwargs) -> Any`, and `available() -> bool`
  (checks optional deps / env keys, like `Git.available()`), plus optional `requires`
  (env-key names / pip extras) for an honest "why unavailable" message.
- **`registry`:** tiny object with `register(tool)`, `get(name) -> Tool | None`, `list()`.
  Built-ins register themselves on import; a pack registers its own tools inside
  `build_pack(cfg)` (so pack tools can close over config/creds).
- **Built-in tools (stdlib, zero new dependency):**
  - `fetch_url(url, *, timeout=…) -> text` — HTTP(S) GET via stdlib `urllib.request`.
  - `html_to_text(html) -> text` — minimal tag-strip via stdlib `html.parser`.
- **Graceful degradation:** a pack checks `tool.available()` (or `registry.get`) before use; an
  unavailable tool is reported, never a hard crash — the pack falls back or the action holds.

## Boundaries (what is core vs pack)
- **Core tool** = domain-agnostic **and** zero / near-zero dependency (the two stdlib tools above).
- **Pack tool** = anything domain-specific, keyed, or heavy: web **search** (e.g. an Exa /
  search-API client — needs a key in `.env` + config), headless/JS rendering, site-shape
  logic. The pack registers these at `build_pack` time; they don't ship in core.
- Tools sit **below** the `Connector` seam — helpers a `fetch()` / action calls, **not** a
  replacement for the seam. The connector contract is unchanged.

## How the website pack will use it (the consumer)
- **`pages` mode** → core `fetch_url` + `html_to_text`. Batteries included, no new dep.
- **`search` mode** → a **pack-registered** `web_search` tool (e.g. Exa) using a config + `.env`
  key, exactly like the LLM providers. Optional; absent key ⇒ `available()` false ⇒ search
  mode disabled, `pages` mode still works.

## Scope / non-goals
- **In:** registry, `Tool` shape, the two stdlib built-ins, availability/degradation, docs.
- **Out (defer):** exposing tools to the **LLM as function-calling** (the idea_2 "agent with
  tools" vision) — v1 tools are internal helpers for pack code only. Also out: a plugin/auto-
  discovery mechanism — explicit registration is enough for one-pack-per-deploy.

## Open questions
- Registration ergonomics: explicit `registry.register(Tool(...))` vs a `@tool` decorator.
- Per-tool config/creds wiring — read from `cfg` at `build_pack` time and close over it
  (consistent with how the connector already gets `cfg.connector`).
- Should built-ins live as one module (`tools/net.py`) or a tool-per-file? Start with one
  `net.py`; split when a third unrelated tool appears.

## Depends on / blocks
- **Blocks** `website-domain-pack` step (1) (the `pages` fetcher) and its `search` mode.
- Pairs with the core's existing "stdlib-only except openai" property — keep it that way:
  core tools add no new dependency.

**Effort:** S–M — small, self-contained core addition (registry + two stdlib tools + docs);
no change to the loop, gate, or existing seams.
