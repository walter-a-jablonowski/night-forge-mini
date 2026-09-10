# Claude Code as an LLM backend (subscription, no API key)

**What:** let a deploy run its analyze step through the local **Claude Code CLI** on the
user's own subscription, instead of an API key. Two apps already do this beside their
OpenRouter/Gemini providers and it works well — a much smarter model for complex passes, at
no per-token cost.

**Effort: M.** Split in two halves that are worth doing in order:
1. **the backend seam** (S) — worth doing on its own merits, see "Clean implementation",
2. **the Claude Code backend + MCP bridge** (M) — the new capability.

## The shape mismatch (the whole design problem)
Every provider we support today is *the same thing*: an OpenAI-compatible chat endpoint.
`ModelWrapper` drives the agentic loop — it calls the model, executes the tool the model
asked for, feeds the result back, logs a `tool_call` span, repeats.

**Claude Code inverts that.** It is an agent, not an endpoint: you hand it a prompt and it
runs the tool loop *itself*. There is no per-step call to make. So it is not a fourth entry
in `providers{}` — a `base_url` + `api_key_env` block cannot describe it, and
`_request_json` / `run_tools` do not apply.

Two consequences:
- **Our tools must go to it, not be called by it.** The CLI takes tools over **MCP**. Our
  `tools/registry.py` is already most of the way there: a `Tool` carries `name`,
  `description` and a `params` JSON schema, which is exactly what an MCP server advertises.
  A small stdio MCP server over the registry is the bridge.
- **Its output must come back in our shape.** The CLI emits stream-json; the tool calls in it
  become our `tool_call` spans and its final text is the proposal JSON that `analyze` returns.

## Reference implementations (both the user's, both working)
- **`C:/Users/Walter/local/grid-view`** — PHP, the closest analogue: a chat sidebar with
  `googleAiStudio | openrouter | ollama | claudeCode`. Read in this order:
  - `lib/ai/claude.php` — the CLI turn. Heavily commented with *why* each flag is there;
    the notes below are condensed from it.
  - `mcp/grid_mcp.php` — the stdio MCP server exposing the same tools every provider gets.
  - `ajax/ai/chat.php` — the dispatch: `claudeCode` takes a different branch, and all
    branches answer in the same message shape.
- **`C:/Users/Walter/local/dev-commander`** — Python, and the better model for the *seam*:
  `lib/agents/base.py` is a 40-line `AgentAdapter` + `register()` registry, with the comment
  that names the goal exactly — *"Adding codex later means writing one module and calling
  register() — no change to the server, the model, or the UI."* Also
  `lib/agents/session_driver.py` for holding a `claude` child over stream-json.

## CLI details worth not rediscovering
Verified in grid-view against CLI 2.1.239:

| flag | why |
|---|---|
| `--output-format stream-json` **+** `--verbose` | plain `json` returns only the final text; the stream is what carries the tool calls |
| `--setting-sources ""` | keeps the user's own CLAUDE.md and memory out of the turn — **measured 27k tokens per session without it vs 319 with it** |
| `--tools ""` | switches the built-in Read/Edit/Bash off, so the agent reaches the disk only through our jailed tools |
| `--allowedTools <names>` | explicit permission. `--permission-mode bypassPermissions` is refused by the local policy classifier and grants more than wanted |
| `--mcp-config <json>` + `--strict-mcp-config` | pass the server inline; **forward slashes only** — a Windows path puts `\x` in the JSON, which is not a valid escape, so it is silently treated as a *filename* and the CLI stops with "file not found" |
| prompt on **stdin** | Windows command lines are length-limited; a long prompt would be truncated |
| `--resume <sessionId>` | continues the CLI-side conversation — **decided against**, see Decisions below |

Process handling (all learned the hard way in grid-view):
- **stderr to a file, not a pipe** — with two pipes to drain, the one you are not reading
  fills and the child blocks forever.
- **Poll with non-blocking reads**; `stream_select`-style multiplexing does not work on pipes
  on Windows. (In Python, `asyncio` subprocess pipes are fine — dev-commander does that.)
- **Always terminate the child in a `finally`** — it reaches the data through the MCP server,
  so an orphan keeps writing after the request is gone.
- Run it in **an empty working directory** so it finds no project it might read as context.

## The safety lesson that matters most
From `lib/ai/claude.php`, and it is worth quoting because the failure is invisible:

> The tools have to be there. Without them the agent does not fail — it **ANSWERS**, from a
> board it makes up, and the reply looks perfectly normal (this happened: a whole invented
> board, tabs and ticket numbers included).

So the turn is **refused** unless the `system`/`init` event reports our MCP server as
`connected`. We need the same check: an analyze pass whose tools never loaded would propose
confident actions against an imagined site. Given our actions then *auto-run* under
git-recoverable, that is worse here than in a chat sidebar.

## Clean implementation (the second half of the ask)
The seam is the real work, and it is overdue independently of Claude Code:

- **`ModelWrapper` is a concrete class with a `fake` flag**, and packs branch on it:
  `if model.fake:` appears in `domains/kb/domain_pack/analyze.py`,
  `domains/website/domain_pack/analyze.py` and `metrics/goal_coverage.py`. So there are
  already **two backend kinds** dispatched by an `if` inside every pack, rather than by
  polymorphism. Claude Code would make three, and the branch would have to be repeated in
  each pack again.
- Proposed shape: a small `Backend` protocol — `complete_json`, `run_tools`, `label`,
  `take_tool_trace` — with `HttpBackend` (today's OpenAI-compatible client), `FakeBackend`
  (what `--fake-llm` means, moved out of the packs) and `ClaudeCodeBackend`. `Engine` picks
  one from config; packs keep calling the same two methods and stop knowing which they have.
- That deletes the `model.fake` checks from pack code, which is the current smell: a pack
  should not implement its own offline mode.
- Config: a backend block that is not shaped like a provider —
  `"backend": "claudeCode"`, `{ "bin": "", "model": "opus", "timeout": 300 }` — rather than
  forcing it into `providers{}` beside `base_url`/`api_key_env`.

## Decisions (2026-09-10, measured on the live runs)

Both open questions are resolved. The measurements behind them are in
`backlog/analyze-context-amplification.md`; the short version is that the cross-run cacheable
prefix is **~856 tokens**, so caching arguments do not decide anything here.

**Backend per ROLE, not per deploy.** Two roles, and resist a general router:
- `analyze` -> Claude Code (the expensive, agentic, judgment-heavy call),
- `judge` -> the cheap HTTP provider. `goal_coverage` is one small call returning a number
  0-10, with no tools; a CLI turn cannot amortise its process spawn + MCP handshake over
  that. It would also not fix that metric's real problem — the judge scored the *same* site
  8.0, then 5.0, then 10.0 across three runs. That is variance, not a weak model.

So `Engine` holds a small role->backend map, and a pack asks for the role it needs. This is
the one decision that changes the seam, which is why it is settled before building.

**Fresh CLI session per run — no `--resume`.**
- Our `history` is already curated and bounded (recent findings, metric trend, rejections,
  failures, predicted-vs-actual). Resuming would double it: the CLI holding the raw
  conversation *and* us injecting our summary of it.
- Determinism — "the JSONL log is the source of truth" is the project's premise. A run must
  see the same context regardless of what some earlier CLI session did.
- One less failure mode: no session id to persist, expire, or go stale.
- It costs almost nothing. Only the system prompt (~856 tokens) is stable between runs; the
  site map, the snippet and the history block all change by design, and the minimum cacheable
  prefix is 512-4096 tokens depending on model. **Within-run** caching — where the real 4-6x
  resend amplification lives — is handled by the CLI itself inside its own session, free.

**What it costs.** On a subscription there is no per-token charge; the currency is session
usage limits (do not quote figures here, they change). A pass is ~44k input + ~7k output
tokens — a modest turn. The exposure is an unattended daemon looping every few minutes, which
is why the stop condition in `run-when-metric-below-target.md` must land before
`scheduler-daemon`, not after. For scale, the same passes at API rates would be ~$0.33/run on
Opus 5 and ~$0.13 on Sonnet 5 (~$239 vs ~$96 a month at 24 runs/day) — that gap is the reason
this task exists.

**Still to verify while building** (not blockers, but do not assume):
- the CLI has no `response_format`, so the proposal comes back as text. Our tolerant
  `_extract_json` + bounded JSON retry already cover exactly this and logged 2 saves in one
  live run — verify it holds for a full proposal payload rather than trusting it.
- `--tools ""` is right for us too: the website pack's artifact IS files, but they must be
  written through our actions (gate, hard constraints, git commit), never by the agent.

## Pairs with
`observability.md` (a stream-json turn is already a trace, and the seam is the one call site),
`data-governance.md` (a subscription backend has different credential handling than an API
key), and `tool-registry` — the MCP bridge is a second consumer of the same registry, which
is a good test of whether that abstraction was right.
