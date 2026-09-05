# Embedding retrieval — top-k by semantic similarity

Split out of `bounded-retrieval.md` (S done 2026-07-06, see `tasks/v done/`), whose keyword
slice bounded the context and left this as the M-sized remainder.

**Effort: M. Priority LOW — quite possibly never.**

## Why it is probably unnecessary
Two changes since it was written have eaten most of its value:
- **agentic-analyze** — the model pulls full entries on demand (`read_entry`, and the website
  pack's `read_page`), so the index slice only has to get the *candidates* roughly right. The
  model corrects a retrieval miss by reading, which is precisely what embeddings would buy.
- **the keyword slice already caps context** — size is bounded regardless of store size, which
  was the actual requirement from `idea_2.md` ("history grows; the context window doesn't").

So this is no longer "finish bounded retrieval" — that is finished. It is "make the candidate
set smarter", which is an optimisation with no known symptom behind it.

## The trigger to build it
A domain whose index grows too large to list even as a bounded slice — i.e. when the *map*
itself (entry ids / site map) stops fitting, not the content. Nothing in the KB or website
packs is near that. Revisit if a third pack has tens of thousands of items.

## Seam (unchanged, no core work)
Context assembly lives inside the pack's `analyze`, so retrieval can be upgraded entirely
within a pack: the core hands over `snippets` + the bounded `history`, and the pack decides
what domain context to add. Adding embeddings would also add the first heavyweight dependency
to a stdlib-only core — a reason on its own to keep it pack-side and optional.
