  > Can Gemini replcae OpenRouter fully?

  **In principle yes, but it hasn't been verified.** Every place that uses OpenRouter goes through the generic `HttpBackend`, so switching to Gemini is a config change: `"provider": "gemini"` plus `GEMINI_API_KEY`. Nothing in the code needs OpenRouter specifically.

  The `HttpBackend` has two jobs, and both should work on Gemini:

  | job | used for | on Gemini |
  |---|---|---|
  | `complete_json` | one-shot analyze, the `goal_coverage` judge, and the judge call in the Claude Code setup | should work. If Gemini rejects `response_format: json_schema`, the backend falls back to a plain call and reads the JSON out of the reply |
  | `run_tools` | agentic analyze with function calling | should work, since Gemini's OpenAI-compatible endpoint supports tools. Untested |

  Caveats:

  - **No live run on Gemini yet.** Every recorded live pass was OpenRouter or Claude Code. Structured output and tool calling are the two places where "OpenAI-compatible" endpoints usually differ, so treat it as unverified until one test round has passed.
  - **Some error handling is tuned to OpenRouter.**
    - The "retry a transient 400 once" logic assumes OpenRouter sends the retry to a different upstream. On Gemini, the same 400 would most likely just fail again, so it costs one extra call.
    - The check for "this provider rejects the parameter" matches error-message words like `response_format` or `not supported`. If Gemini words the rejection differently, the backend won't remember it, and every structured call pays one wasted attempt before the plain fallback.
  - **Model choice.** OpenRouter gives you many vendors' models through one key. Gemini only gives you Gemini models. That's fine if Gemini is what you want.
  - **Quotas.** Gemini's free tier has its own rate and daily limits. The long run ended on OpenRouter's free cap of 50 requests a day, and a similar ceiling could apply.

  For now, Gemini is a good fit for the `goal_coverage` judge next to the Claude Code backend. It's a small call, and it would fix the current 401. Running the whole analyze pass on Gemini needs one supervised live test first, then you can call it a full replacement.


  > Shortly list things again where we ned Gemini or OpenRouter and that can't be done by claude with a short commenty why

  Only a few things still need Gemini or OpenRouter. The first two are routing choices in our code, not things Claude can't do:

  | what | why it needs an HTTP provider today |
  |---|---|
  | **`goal_coverage` judge** (website) | `ClaudeCodeBackend.complete_json` always hands one-off calls to the HTTP provider. That was a deliberate choice: starting a process and connecting the MCP server for one small number costs too much, and the CLI has no way to force a JSON reply. Claude could do the judging; there's just no code path for it yet. |
  | **One-shot analyze** (`analyze_tool_steps: 0`) | One-shot analyze also uses `complete_json`, so it quietly runs on HTTP even with `backend: claudeCode`. This is refinement §2 in the backlog, and nothing warns about it yet. |
  | **Lever 1: dropping old tool results from the context** | Only possible where we control the message list, which means the HTTP backend. The Claude CLI runs its own loop, so we can't change its history. It's a cost saving, not something you can't do without. |
  | **Live-testing the HTTP backend's own safeguards** (400 retry, structured-output fallback) | These only exist on the HTTP path, so only a real provider can exercise them. |

  Separately, the `web_search` tool needs a Tavily or Exa key, not Gemini or OpenRouter. Without one, that tool is simply turned off, whichever backend runs the pass.

  Everything else (the agentic analyze for both packs and every action) already runs on Claude Code through your subscription.

## Verified live 2026-10-10 (Gemini, `gemini-flash-latest` = gemini-3.8-flash)

| question | result |
|---|---|
| structured output (`json_schema`) | works, accepted natively (`_schema_ok` True) |
| `run_tools` function calling | was **broken**: 400 `Function call is missing a thought_signature` at step 2. Gemini 3 attaches the signature to each tool call and requires it back; we rebuilt the assistant turn field by field and dropped it. **Fixed**: the turn is echoed as the SDK returned it (`_echo_turn` in `backends/http.py`), which also covers OpenRouter's `reasoning_details`. Re-verified live: 2 reads + final answer |
| free-tier quota | **5 requests/min, 20/day per model**. Enough for the judge (1 call per pass) next to Claude Code, not for a whole HTTP analyze pass. The 20/day ran out within one test session |
| overload | `503 high demand` happens; the SDK's default retries + backoff made one probe wait > 5 min silently |
| `goal_coverage` on a 3-page nutrition site | 9.0-9.5, so a target of 8 is met after one pass for this goal |

Still unverified on Gemini: a full analyze pass on the HTTP backend (quota) and the transient-400 retry.
