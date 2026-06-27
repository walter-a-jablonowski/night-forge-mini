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
- **Package `night_forge_mini/tools/`.** Mirrors the existing dataclass-seam style
  (`Pack`, `Action`) — no framework. `tools/registry.py` holds the `Tool` dataclass +
  `Registry` class + one default module-level `registry` instance.
- **File layout per tool:** a **simple** tool is a single file `tools/MY_TOOL.py` exposing a
  `TOOL` (and its `run`); a **complex** tool gets its own package `tools/MY_TOOL/`. The same
  convention applies wherever a tool lives — core `tools/` for built-ins, the pack for
  pack-owned tools.
- **`Tool` dataclass:** `name`, `description`, `run(**kwargs) -> Any`,
  `requires: list[str]` (env-var names the tool needs), `available() -> bool`
  (default: all `requires` present in `os.environ`; honest about why it's off, like
  `Git.available()`).
- **`Registry`:** tiny object — `register(tool)`, `get(name) -> Tool | None`, `list()`. One
  module-level singleton `registry`, pre-populated with built-ins; `Registry` stays
  instantiable so tests can use a fresh one. Registration is **explicit** — no `@tool`
  decorator, no import-time self-registration inside tool modules: `tools/__init__.py` imports
  each built-in and calls `registry.register(mod.TOOL)` (the whole built-in set visible in one
  place); a **pack** registers its own tools inside `build_pack(cfg)` via the same call (so
  they can close over config/creds).
- **Built-in tools (stdlib, zero new dependency), one file each:**
  - `tools/fetch_url.py` → `fetch_url(url, *, timeout=…) -> text` (stdlib `urllib.request`).
  - `tools/html_to_text.py` → `html_to_text(html) -> text` (stdlib `html.parser`).
- **Credentials & config:**
  - **Secrets → `.env`**, provided by the operator when they merge the blank app + a domain
    pack into a deploy folder. A tool names the **env-var** it needs (never the secret) via
    `requires` / an `api_key_env`-style config key — exactly like `providers[*].api_key_env`;
    `available()` is False when the key is missing, so the capability disables gracefully.
  - **Non-secret params → `config.json`** (timeouts, result counts, allowed domains, …), read
    by the pack at `build_pack` time, like `cfg.connector`.
  - Each pack documents the env-vars its tools need (its README / `.env.example` additions);
    the operator merges them into the deploy `.env`.
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

## Decisions (resolved)
- **Creds (user):** tool secrets live in **`.env`**, provided by the operator at deploy (the
  merged blank+pack folder); tools reference the env-var name (`api_key_env` pattern).
  Non-secret params live in `config.json`.
- **File layout (user):** simple tool = `tools/MY_TOOL.py`; complex tool = `tools/MY_TOOL/`
  package.
- **Registration:** explicit `registry.register(Tool(...))` — no decorator, no import-time
  magic. Built-ins wired in `tools/__init__.py`, pack tools in `build_pack(cfg)`. One
  mechanism: a module-level decorator can't close over `cfg`, so explicit is the common
  denominator for both core and pack tools.
- **Built-ins:** one file per tool (`fetch_url.py`, `html_to_text.py`), not a single `net.py`.
- **Registry scope:** one module-level singleton (single-process, one-pack-per-deploy);
  `Registry` is instantiable so tests can use a fresh instance.

## Depends on / blocks
- **Blocks** `website-domain-pack` step (1) (the `pages` fetcher) and its `search` mode.
- Pairs with the core's existing "stdlib-only except openai" property — keep it that way:
  core tools add no new dependency.

**Effort:** S–M — small, self-contained core addition (registry + two stdlib tools + docs);
no change to the loop, gate, or existing seams.
