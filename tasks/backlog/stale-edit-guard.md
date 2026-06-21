# Stale-Edit Guard (optimistic concurrency for held actions)

**Status: DONE (S).** Implemented in the KB pack: a proposed `edit_entry` is stamped with a
body fingerprint (`KnowledgeBase.fingerprint`, a sha1 of the current body) via
`_stamp_edit_base` in `domain_pack/analyze.py`; at approval time `edit_entry` recomputes the
body hash and **refuses with an `error` outcome** ("changed since proposed; re-run to
re-propose") if it differs — so an intervening change is never silently overwritten. The
guard is opt-in per action (no `base` → proceeds), so other callers are unaffected.

**Original problem.** Held actions carry a payload computed against the KB snapshot from
**propose time**, and `edit_entry` **overwrites the whole body** (no merge). Nothing
re-validated the payload against the *current* file at approval time, so approving a stale
held action silently clobbered any change made during the pending window — a **lost update**,
not byte-level corruption.

## How it bites (default KB config)
1. Run N-1 proposes `edit_entry(vpn-setup, …)` → held (`reversible=False`).
2. Run N auto-runs `flag_contradiction(vpn-setup)` (allow-listed) → appends a note to the body.
3. You approve the run N-1 edit → body is replaced with the **stale** payload → the
   contradiction note (and any other intervening edit) is gone.

Also: two pending `edit_entry`s on one entry have **no enforced approval order** → last
approved wins, which may not be the newest information.

## Why it's only bounded today
- `edit_entry` (the only overwrite) is **always human-gated**, so a person sees it — but the
  CLI shows **no diff vs. current content**, so a stale overwrite can be approved unknowingly.
- `add_entry` is create-only (can't clobber); `flag_contradiction` / `mark_stale` are additive.
  So the hazard is specifically **held `edit_entry` overwrites across the pending window**.

## Fix — optimistic concurrency (DONE)
- ✅ At **propose** time, the current **body content hash** is recorded as `payload.base`
  (`_stamp_edit_base` → `KnowledgeBase.fingerprint`). A body hash (not the `updated`
  timestamp) is used on purpose: `flag_contradiction` appends to the body **without** bumping
  `updated`, so a timestamp check would miss exactly the lost-update example below.
- ✅ At **approval** time, `edit_entry` recomputes the body hash; if it differs from `base`,
  it **refuses with an `error` outcome** instead of a blind overwrite, forcing a fresh
  re-propose against current state.
- Verified: stale approve → `ran FAILED (… changed since proposed)` with the intervening
  change preserved; clean approve → `ran ok`; no `base` → proceeds (back-compat).

## Seam / related
- The check lives entirely in the KB pack (`domain_pack/actions.py` + the propose path in
  `analyze.py`); **no core change**. A pack with append-only / CRDT-style actions wouldn't
  have this issue at all.
- Complemented by `approval-ui.md` (diff + edit-before-approve at review time).

**Effort:** S — done.
