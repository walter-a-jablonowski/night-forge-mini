# One analyze pass sends its context 4-6 times over

**Measured 2026-09-10** on the website deploy's real runs. Every agentic step resends the
whole conversation so far, so the content that actually enters a pass is billed several times.

**Effort: S-M.** A `run_tools` change in `llm.py`; no pack change.

## The measurement
`BASE` = the system prompt + rendered user context for one pass = **8,160 chars**
(3,252 system + 4,908 site map / snippet / history). Tool-result sizes come from the
`chars` field the store already records on every `tool_call` span.

| run | steps | tool results | input actually sent | output | amplification |
|---|---|---|---|---|---|
| run-b1e9637c | 5 | 13,147 | 94,112 | 18,204 | 4.4x |
| run-393b4eee | 6 | 16,404 | 128,587 | 27,913 | 5.2x |
| run-a257a9c6 | 7 | 20,499 | 166,207 | 27,594 | **5.8x** |

So run-a257a9c6 put ~28.7k chars of distinct content in front of the model and sent ~166k.
At ~3.8 chars/token that is roughly **44k input + 7k output tokens for one pass** — about
$0.33 at Opus 5 API rates, $0.13 at Sonnet 5. It grows with the site: the amplification rose
monotonically as pages were added, because each new page is both a bigger `read_page` result
and one more step to resend everything before it.

*(Chars/token is an estimate, not a tokenizer count — no API key in this repo to run
`count_tokens`. The chars are exact.)*

## Why it is worth fixing even though caching hides it
Claude Code and the Anthropic API both cache within a session, so the resends are cheap
*there*. Two reasons that is not the whole story:
- **OpenRouter/Gemini/Ollama runs pay it in full** — that is the deploy default today, and
  those bills are per-token with no automatic caching.
- **The context window is the real ceiling.** A site four times this size would not merely
  cost four times more; the resent history is what eventually stops a pass from fitting, and
  `site_map_max` bounds the map but nothing bounds the accumulated tool results.

## Levers, cheapest first
1. **Drop stale tool results from the resent history.** After the model has read a file and
   moved on, the full body no longer earns its place in every later request — replace it with
   a one-line placeholder (`[read_page index.html — 3,370 chars, superseded]`). This is what
   the Anthropic API exposes as context editing (`clear_tool_uses`), and the same idea works
   by hand for any provider, because we own the message list in `run_tools`.
2. **Cap a single result.** `result_cap` defaults to 16,000 chars *per result* and nothing
   caps the total. A whole-file read is the point of `read_page`, so cap the sum instead of
   the item, and tell the model when it was trimmed.
3. **Refuse a repeated identical call.** run-a257a9c6 read `style.css` twice (3,387 chars,
   billed on every later resend). One cache per run keyed on `(tool, args)` returning
   "already read above" is a few lines in `_run_tool` — modest on its own, but free.

## Careful
- The model reads a file *because* it is about to rewrite it — a body dropped too eagerly
  costs a re-read, which is worse than keeping it. Drop by age (superseded by later steps),
  never the most recent result.
- Anything removed from the resent history must still be logged in full: the `tool_call`
  spans are the audit trail and a trimmed prompt must not become a trimmed record.
- Measure again after, with the same method as above (the store already has every number
  needed) — the amplification ratio is the metric to watch, not the raw char count, which
  legitimately grows with the site.

## Related
`claude-code-backend.md` (the decision to run analyze on Claude Code was taken on these
measurements — and its within-session caching is exactly what makes this less urgent there),
`observability.md` and `roi-measurement.md` (this is the first concrete case where per-run
token/cost visibility would have told us without a hand-written script).
