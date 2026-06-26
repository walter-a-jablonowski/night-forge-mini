# Git Integration (version the materialized artifacts)

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
  Sketch:
  ```json
  "git": { "enabled": true, "versions": ["site"], "granularity": "per_run",
           "remote": "", "branch": "main" }
  ```
- **Separate repo, NEVER the source `.git/`.** The artifact repo is a distinct repo rooted
  at the artifact/data dir (or deploy root). A hard guard must refuse to commit if the
  target resolves to the project's source repo root. For testing, `/try` is the deploy
  sandbox, so the test artifact repo lives there (e.g. `try/data/site/`).
- **Hook point:** a small optional helper (e.g. `commit_artifacts(dir, message)`) invoked
  after successful `outcome`(s); commit message references the `run_id` (+ `action_id` for
  `per_action`) so the JSONL log and git history stay cross-linkable.

**Open questions:**
- Shell out to a `git` binary vs. a lib (e.g. `dulwich`/`GitPython`) — dependency tradeoff.
- Auth for remote push (token via `.env`, SSH) — define for the GitHub-push path.
- Auto-init the artifact repo on first run vs. require a pre-initialized repo.

**Effort:** S (local commit-on-outcome) → M (config, remotes, per-pack policy).
