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

## What to change — analysis 2026-10-11

Three ways to reach Claude, and what each needs today:

| route | how | status |
|---|---|---|
| Claude Code CLI (subscription) | `backend: claudeCode` | works for the AGENT role only; one-shot calls are hard-wired to the HTTP provider |
| Claude API, OpenAI-compatible endpoint | `base_url https://api.anthropic.com/v1/` + `ANTHROPIC_API_KEY` in `providers` | config only, untested. Caveats below |
| Claude via OpenRouter | `model: anthropic/claude-…` | config only, untested |

The real gap is not the HTTP layer, it is ROUTING: a deploy has two roles, and only one is
configurable.

```
role        method          backend http      backend claudeCode
agent       run_tools       provider          CLI
one-shot    complete_json   provider          provider  (fixed, cannot be the CLI)
```

### 1. Make the one-shot role routable (M) — the main change

**DONE 2026-10-11.** `one_shot` in config: a key of `providers` or `claudeCode`; empty =
`provider` when configured, else the backend itself (old behaviour kept).
`claudeCode.oneShotModel` picks the judge's model.
- code: `backends/routed.py` (`RoutedBackend`, `build`), `ClaudeCodeBackend.complete_json`
  (a tool-less turn with `--json-schema`), `Config.provider(name)`; FakeBackend no longer
  needs a provider. Tests: `test_routing.py` (13), one-shot CLI tests (5). 219 passed.
- live 2026-10-11, `try/website`: analysis labelled `claudeCode:sonnet + one-shot
  claudeCode:haiku`, `goal_coverage=8.0` measured by the CLI judge, no metric error.
- by accident: the machine slept after the proposal was written; the 5 actions were left
  HELD in the inbox, the site repo clean — an interrupted pass fails safe.

- Verified 2026-10-11: the CLI HAS structured output. `claude -p --json-schema '<schema>'`
  with `--tools ""` and an empty MCP config returned the validated object as
  `structured_output` on the `result` event; a haiku judge call took ~6.5 s end to end.
  `claude_code.py` still says "the CLI has no structured-output parameter" — that premise of
  the HTTP split is outdated (the spawn cost remains: ~6.5 s vs ~1-2 s on Gemini).
- Change: a `one_shot` (judge) setting that names a route — an HTTP provider OR the CLI —
  independent of `backend`. E.g. `"oneShot": "claudeCode"` | `"oneShot": "gemini"`.
- Gains:
  - a subscription-only deploy (no Gemini/OpenRouter key at all),
  - `backend: http` with a DIFFERENT judge provider (analyze on OpenRouter, judge on Gemini),
  - refinement §2 (one-shot analyze silently on HTTP) disappears instead of needing a warning.
- The no-tools refusal (refinement §3) stays for `run_tools`; a one-shot CLI call is a
  different method with no MCP server to fail, so it does not need relaxing.

### 2. JSON repair parity on the CLI path (S)
- HTTP: a parse failure is retried twice with the error fed back (`_request_json`).
- CLI: `_extract_json(turn["text"])` raises and the whole pass is lost, tool reads included.
- Fix: pass `--json-schema` on the agent turn too (constrained at the source), and/or resume
  the session (`--resume <session_id>` is in the stream) with the JSON-fix prompt.

### 3. Truncated output is not detected — all providers (S)
- No `max_tokens` is ever sent and `finish_reason` is never read.
- A website proposal carries whole HTML pages; if it hits the provider's default output cap,
  the cut-off JSON is treated as a FORMAT error, and the retry asks for "the SAME proposal
  again" — which truncates the same way. Three calls, then a lost pass.
- Fix: per-provider `max_tokens`; on `finish_reason == "length"` raise a clear LLMError
  ("output truncated — raise max_tokens or propose fewer/smaller actions") instead of a
  JSON retry. Pairs with `salvage-partial-model-json.md`.

### 4. A provider probe command (S)
- "Interchangeable" is only provable per provider, and each live pass so far found a quirk
  (Gemini thought_signature, OpenRouter flaky 400s, Gemini 5 rpm).
- `python -m night_forge_mini probe`: one `complete_json` with schema + one 2-step
  `run_tools` against the configured route(s); report schema accepted / ignored, tool loop
  ok, state echo ok, latency, finish_reason. Minutes instead of a supervised pass.

### 5. Provider quirks as config, not code (XS each)
- `temperature` is hard-coded 0.2. OpenAI reasoning models (reachable via OpenRouter) reject
  it; that 400 contains "not supported", so `_param_rejected` would wrongly switch structured
  output off and the retry still fails. → per-provider `temperature` (null = omit).
- The transient-400 retry assumes OpenRouter re-routing; on a direct provider it is one
  wasted call. → per-provider flag, default on only for openrouter.
- Gemini free tier: `max_retries ~8` (documented in config.example.json 2026-10-11).

### 6. Anthropic via the OpenAI-compatible endpoint — known limits (from Anthropic's docs)
- `response_format` is IGNORED silently: `_schema_ok` becomes True although nothing was
  constrained. The prompts already ask for JSON and the JSON retry covers it, but a probe
  (4) should report "ignored", not "native".
- No prompt caching on that endpoint: every tool step resends the whole conversation at
  full price — the amplification measured in `analyze-context-amplification.md`.
- A native Anthropic backend (Messages API: real structured outputs + caching) is the
  answer if Claude-over-API is used seriously. Not before 1-5 and a probe show the need.

### 7. Switching the judge mixes scales in the metric history (S) — found live 2026-10-11
- The same 9-page site: Gemini 2.5 Flash judged 9-10, Claude haiku 8.0. `targets.py` reads
  the history as one series, so the switch alone looked like a drop, and the next
  `run-once` stopped with "stopped improving" (best 10.0 by Gemini, not beaten by haiku).
- The analysis record already stores the label (`... + one-shot claudeCode:haiku`), so the
  fix is cheap: compare a judged metric only within one judge — a change of judge starts a
  fresh series (the last-known value for "met" too). Code metrics are unaffected.
- Until then: after changing `one_shot`, expect one misleading stop; new input or a fresh
  log resets it.

### Order
1 (removes the need for a second vendor) → 3 (silent pass loss, every provider) → 2 → 4 → 5.
6 only on demand. Nothing here blocks current use: claudeCode + Gemini judge works.
