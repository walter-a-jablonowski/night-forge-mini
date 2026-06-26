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

**Design sketch:**
- A small optional helper (e.g. `commit_artifacts(paths, message)`) the pack calls after a
  successful `outcome`, gated by a config flag (`"git": {"enabled": true, "dir": "data/site"}`).
- Commit message references the `run_id` + `action_id` so log and git stay cross-linkable.
- Keep it pack-side (or a thin shared util) so the core stays domain-agnostic; no auto-init
  of unexpected repos.

**Open questions:**
- One repo for the whole deploy vs. per-artifact-folder repo?
- Commit granularity: per action, per run, or batched?
- Remotes/push and auth — in scope or local-only first?
- Relationship to the existing project `.git/` (must never touch it).

**Effort:** S (local commit-on-outcome) → M (config, remotes, per-pack policy).
