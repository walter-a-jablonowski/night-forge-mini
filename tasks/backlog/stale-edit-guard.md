# Stale-Edit Guard (optimistic concurrency for held actions)

**Domain-pack concern (KB).** Held actions carry a payload computed against the KB
snapshot from **propose time**, and `edit_entry` **overwrites the whole body** (no merge).
Nothing re-validates the payload against the *current* file at approval time, so approving
a stale held action silently clobbers any change made during the pending window — a
**lost update**, not byte-level corruption.

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

## Fix — optimistic concurrency (small)
- At **propose** time, record the entry's `updated` timestamp (or a content hash) in the
  action payload.
- At **approval** time, `edit_entry` compares it to the current file; if the entry changed
  since it was proposed, **refuse with an `error` outcome** ("entry changed since proposed;
  re-run to re-propose") instead of a blind overwrite.
- This forces a fresh re-propose against current state rather than a lost update — no UI needed.

## Seam / related
- The check lives entirely in the KB pack (`domain_pack/actions.py` + the propose path in
  `analyze.py`); no core change. A pack with append-only / CRDT-style actions wouldn't have
  this issue at all.
- Complemented by `approval-ui.md` (diff + edit-before-approve at review time).

**Effort:** S.
