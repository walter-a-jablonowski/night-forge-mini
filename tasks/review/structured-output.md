# Structured Output — replace regex-JSON extraction

**From the 2026-07-05 core review.**

**What:** Stop parsing the proposal JSON out of prose with `_extract_json` (regex over the
completion text in `llm.py`). Use the provider's native mechanism instead:
`response_format: json_schema` (OpenAI-compatible; OpenRouter/Gemini support it) or a
single forced tool call whose parameters are the proposal schema.

**Why:**
- `re.search(r"\{.*\}")` over prose is the fragile 2023 way — it breaks on nested braces in
  body text, markdown fences with commentary, or partial JSON, and each failure kills a run.
- A declared schema also removes a whole class of malformed-output cases before the core's
  `sanitize_actions` even sees them (that guard stays — defense in depth).

**Design sketch:**
- `complete_json(system, user, schema=None)` — when `schema` is given, send it as
  `response_format`; fall back to the current extraction only if the provider rejects the
  parameter (Ollama models vary). One place: `llm.py`.
- The proposal schema (`finding`, `actions[]` with `name`/`target`/`rationale`/`payload`)
  is defined once in the core; a pack may extend the `payload` part.

**Effort:** S. Do before agentic-analyze.md — same call site, halves its risk.
