# Git Integration (version the materialized artifacts)

**Status: DONE (S) — command-line variant.** Implemented in core `night_forge_mini/git_sync.py`
(`Git`, shells out to the `git` binary), wired into `loop.py` (`Engine._commit_action` /
`_commit_run` / `_commit_resume`), config via `Config.git` + the `"git"` block, results shown
in `cli.py` (`_print_git`). Documented in `blank/README.md`. The in-process **library**
back-end is split out to `git-library.md`.

**What:** Optionally commit a domain pack's **materialized artifacts** (the KB markdown
under `data/kb/`, a future website's files under `data/site/`, etc.) to a git repo, one
commit per applied action / per run. The JSONL log stays the source of truth; git adds
file-level version history, diffs, and easy rollback for the materialized output.

**Why now:** The planned **website** domain pack does destructive, file-shaped edits —
change layout/design, edit content, **create or remove sub-pages**. Unlike the KB (where
`add_entry` is create-only and most actions are additive), a website pack overwrites and
deletes files, so a per-change commit history is the natural way to make those changes
inspectable and reversible.

**Why deferred:** The core already gives an append-only audit log + the reversible hard
floor; git is a *convenience* on top of the materialized layer, not required for safety.
It also adds a dependency/process concern (a git binary or a lib, repo init, auth for
remotes) that shouldn't leak into the domain-agnostic core.

**Value:**
- Real diffs + `git revert` for file artifacts (esp. irreversible `edit_entry` / page deletes).
- A second, human-familiar view of "what changed" alongside the JSONL trace.
- Makes the materialized output portable / deployable (push a site repo).

**v1 preparation (already in v1):**
- Every change flows through `decide()` and is recorded as `decision` + `outcome` — the
  exact hook points where a commit could be made.
- Actions own all file writes inside the pack; a commit step can wrap the pack's writes
  without a core change.

**Design decisions (resolved):**

- **Commit unit = the whole artifact folder snapshot.** Git snapshots whatever is staged,
  so the model is `git add -A` in the artifact dir + commit — the *whole* materialized
  folder at that point, not per-file deltas.
- **Granularity is a config setting (`per_run` default, `per_action` optional).** A
  `run_once` pass is the atomic loop step, so the default is one commit after the run
  completes *if any `outcome` succeeded*. `per_action` gives finer history (one commit per
  successful action) at the cost of more commits per run.
- **Local-first, push-if-easy (tiered, never breaks the loop):**
  1. git enabled → always commit **locally** first.
  2. remote configured + reachable → also **push**.
  3. remote missing/unreachable → stay **local-only**, log a warning, do **not** fail the
     loop (same spirit as the gate's "never half-commit" failure handling).
- **Config lives in CORE `config.json` (optional; absent = off).** The git block is
  operator/infra (like `provider`, `paths`, `allow_list`): enable flag, remote URL,
  granularity, repo dir, creds via `.env`. The **pack** only declares *which* path is its
  materialized artifact — and those paths already live in `config.paths` (e.g. `kb`,
  future `site`), so the git block just references which path key(s) to version. This
  keeps the existing split: core config = operator settings, pack = domain definition.
  Shipped shape (a single `repo_dir` staged whole with `git add -A`, simpler than the
  earlier per-path-key `versions` idea):
  ```json
  "git": { "enabled": true, "repo_dir": "data", "granularity": "per_run",
           "remote": "", "branch": "main" }
  ```
- **Separate repo, NEVER the source `.git/`.** The artifact repo is a distinct repo rooted
  at the artifact/data dir (or deploy root). A hard guard must refuse to commit if the
  target resolves to the project's source repo root. For testing, `/try` is the deploy
  sandbox, so the test artifact repo lives there (e.g. `try/data/site/`).
- **Hook point:** a small optional helper (e.g. `commit_artifacts(dir, message)`) invoked
  after successful `outcome`(s); commit message references the `run_id` (+ `action_id` for
  `per_action`) so the JSONL log and git history stay cross-linkable.
- **Use the `git` CLI (shell out), not a library.** git is almost always installed; the CLI
  reuses the user's existing auth (SSH keys / credential helper / token) so the app manages
  no credentials. If `git` isn't on PATH, the feature stays disabled (never breaks the
  loop). "GitHub installed" just means git is installed — nothing GitHub-specific is
  embedded; push targets whatever `remote` URL is configured.
- **Repo must be pre-initialized (auto-init deferred).** For now the operator creates the
  artifact repo themselves (`git init` in the artifact dir, optionally `git remote add`).
  The app commits/pushes to an existing repo and does NOT init one. This must be documented
  as a setup requirement in the deploy README when the feature ships.

**Resolved at implementation:**
- **git CLI, not a library** — done; library variant deferred to `git-library.md`.
- **Pre-initialized repo required** — the core never runs `git init`; documented in
  `blank/README.md` and both `config.json`s.
- **Repo-root guard** — `available()` refuses unless `git rev-parse --show-toplevel` equals
  `repo_dir`, so it can never commit to a parent/source repo.
- **Push is best-effort** — a failed push keeps the local commit and only warns.

**Open questions (remaining):**
- Auth for remote push (token via `.env`, SSH) — relies on the operator's existing git auth
  today; revisit if a deploy needs app-managed creds.
- Auto-init the artifact repo on first run (deferred; pre-init required for now).

**Effort:** S — done (CLI, local + push). Library back-end (M) tracked separately.
