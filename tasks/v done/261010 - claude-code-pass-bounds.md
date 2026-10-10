# Claude Code passes were bounded by nothing but the timeout

**Found and fixed 2026-10-10**, first live runs on a new machine (`try/kb`, `try/website`,
`backend: claudeCode`, model `sonnet`, no API keys).

## What was wrong

| bound | HTTP backend | Claude Code backend (before) |
|---|---|---|
| `max_steps` (`analyze_tool_steps`) | loop limit | swallowed by `**kwargs` |
| `result_cap` / `result_budget` | `_ToolBudget` | swallowed by `**kwargs` |
| repeated identical read | "already read above" | re-ran and re-sent the body |

Levers 2+3 of `analyze-context-amplification.md` had been built inside `backends/http.py`
only. When the Claude Code backend landed, the bounds the packs pass in were accepted and
dropped, so `analyze_tool_steps: 8` meant nothing there.

**Measured:** one kb pass read `expense-policy` 5×. One website pass read `index.html` 5×
and `style.css` 4×. A raw stream-json capture confirmed these were the model's own calls
(distinct `tool_use` ids), not duplicated events in our parser. Sonnet on the CLI re-reads
far more than the HTTP runs measured earlier (1 duplicate in 3 runs).

## Fix

```
tools/pass_budget.py   PassBudget (repeat · take · remember) + RESULT_CAP/RESULT_BUDGET
   ├─ backends/http.py        uses it inside its own loop (was the private _ToolBudget)
   └─ mcp_server.py ToolPass  uses it per CLI turn + a call budget (--max-calls)
backends/claude_code.py   run_tools takes the bounds explicitly and passes them as
                          server args: --max-calls --result-cap --result-budget
```

- The MCP server process lives exactly one CLI turn, so its state is the pass state.
- `--max-calls` counts tool **executions**. The server cannot see model turns, so a turn
  with 3 parallel reads spends 3. That's stricter than HTTP steps. A cached repeat spends
  nothing.
- Past the budget the agent gets an error result telling it to return the JSON now. The
  turn is not cut off (`claude --max-turns` would end it without an answer).
- A span answered from the cache is marked `cached: True` in the parser, as on HTTP.
- `Backend.run_tools` doc now says the bounds are part of the contract.

## Verified
- tests: 7 new (5 MCP server incl. `main()` arg parsing end to end, 2 backend), 160 → 167
- **live:** same real website analyze prompt rerun → 3 repeats answered with the 118-char
  pointer instead of the bodies; pass completed normally (8 turns).

## Not done / cannot be done
- Lever 1 (dropping stale results from the resent history) is impossible on the CLI, because
  the agent owns its message list. It stays an HTTP-only lever.
- Spans from the CLI record what the agent RECEIVED (`chars`), not the full file size,
  because the full size never leaves the server process. Fine for counting, not for an exact
  amplification measurement.
