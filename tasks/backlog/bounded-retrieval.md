# Bounded Retrieval — relevant-slice context (finish idea_2's "bounded context")

**Partially in v1.** `idea_2.md` (Running v1 → *Bounded context*) requires: *"Ingest
assembles recent N runs + same-domain relevant slice, never the full store. History grows;
the context window doesn't."* v1 does the **history** half but not the **slice** half:

- ✅ Generic history is bounded — the core feeds `recent_findings[-recent_runs:]`.
- ❌ Domain context is the **full** KB — the KB pack's `analyze` calls `kb.index()`, which
  returns *every* entry. As the KB grows, this slice grows without bound — the opposite of
  "the context window doesn't [grow]."

**Why it's safe to defer:** at v1 scale the KB is small, so the full index is cheap and is
the simplest correct thing. Smarter retrieval (rank/select the most relevant entries for the
incoming snippets) is a real component (keyword index or embeddings), not a one-liner.

**Seam already in v1 (no core change needed later):** context assembly lives **inside the
pack's `analyze`** (the swappable strategy), and the core already bounds the generic history.
So retrieval can be upgraded entirely within a pack:
- The core hands the pack `snippets` + bounded `recent_findings`.
- The pack decides what domain context to add (today: the whole index; later: a top-k slice).

**Adds later:**
1. **S** — cap the index (most-recent / top-N) or a keyword slice keyed to the incoming
   snippets' terms, so context size is bounded regardless of KB size.
2. **M** — embedding retrieval (top-k by similarity to the new snippets), optionally a shared
   retrieval helper in core that any pack can call.

**Effort:** S (cap / keyword slice) → M (embedding retrieval).

**Note:** `idea_2.md` lists bounded context as a v1 item (not under "Explicitly NOT in v1").
This file tracks finishing the unimplemented *relevant-slice* half; decide whether to also
annotate the spec.
