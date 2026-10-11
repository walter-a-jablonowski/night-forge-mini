# No agentic pass could run on Gemini 3 — the tool loop dropped provider state

**Found and fixed 2026-10-10**, first live test of the HTTP backend on Gemini
(`gemini-flash-latest` = gemini-3.8-flash).

`400 Function call is missing a thought_signature in functionCall parts` on the **second**
step of every `run_tools` pass. Gemini 3 attaches a `thought_signature` to each tool call
(`tool_calls[].extra_content.google`) and requires it back on the next request.
`HttpBackend.run_tools` rebuilt the assistant turn field by field (`id`, `type`, `function`),
which keeps only what we knew about. OpenRouter's reasoning models carry
`reasoning_details` the same way, so the same loss would have degraded them silently.

**Fix:** `_echo_turn(msg)` sends the turn back as the SDK returned it
(`model_dump(exclude_none=True)`, extra fields included), minus response-only
`annotations`, with `content` normalised to a string.

**Test hygiene:** the `run_tools` tests built responses from `SimpleNamespace`, which can
neither carry provider extras nor prove that the code reads the SDK's real object. That's the
same trap as long-run §7. The helpers now build real `ChatCompletion` objects. All 13 existing
tests held, and the new one (`test_provider_state_on_the_assistant_turn_is_echoed_back`)
failed first.

**Verified live:** 2 `read_page` calls + final answer on Gemini after the fix.

Also seen, not ours: `503 high demand` (the SDK's default retries + backoff made one probe
wait > 5 min silently), and free-tier quota of 5 requests/min and 20/day per model. Details in
`v done/261011 - interchangeable-llms.md`.
