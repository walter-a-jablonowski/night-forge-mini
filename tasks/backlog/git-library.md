# Git Integration — library variant (no `git` binary)

**Status: deferred.** The CLI variant is **DONE** (see `git-integration.md`): the core shells
out to the installed `git` binary (`night_forge_mini/git_sync.py`). This task is the
alternative back-end: do git operations **in-process via a Python library** instead of
shelling out.

**What:** Make `Git` (or a sibling impl behind the same interface) commit/push the
materialized artifacts using a library — `dulwich` (pure-Python, no binary needed) or
`GitPython` (a wrapper that still needs the `git` binary).

**Why it might be wanted:**
- **No `git` binary** on the host (locked-down containers, serverless) — `dulwich` removes the
  PATH dependency entirely.
- **Structured errors / no text parsing** — library calls return objects, not stdout to scrape.
- **Tighter control** — stage specific paths, inspect diffs, build commits programmatically.

**Why deferred:**
- The CLI variant already works and **reuses the operator's existing git auth** (SSH key /
  credential helper / token). A library has to re-solve auth, especially for push.
- Adds a dependency; `dulwich`'s remote/push + auth story is more limited than the CLI's.
- No concrete need yet — revisit when a deploy target lacks a `git` binary.

**Design (drop-in behind the existing seam):**
- Keep the current `Git` public surface: `from_config(cfg)`, `available()`, `commit(message)`
  returning the same status dicts (`ok` / `noop` / `skipped` / `error`, plus `push`).
- Select back-end via config, e.g. `"git": { ..., "backend": "cli" | "dulwich" | "gitpython" }`
  (default `cli`). The Engine wiring in `loop.py` stays unchanged.
- Preserve the same safety rules: disabled unless `enabled`, repo must be pre-initialized and
  rooted exactly at `repo_dir` (never a parent/source repo), push failure never breaks the loop.

**Open questions:**
- Auth for push via library (token in `.env`, SSH agent) — the main reason the CLI is easier.
- `dulwich` vs `GitPython` (pure-Python vs binary-wrapper) — pick per the "no binary" goal.

**Effort:** M (auth + back-end selection + parity tests with the CLI variant).
