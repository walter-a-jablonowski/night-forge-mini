# Website analyze: the model calls ACTIONS as if they were TOOLS

**Found 2026-09-04** in the first real-model run of the website pack (`try/website/`,
run-7eb9729b, `dots-studio/dots-3-note-preview:free`). `--fake-llm` cannot surface this —
the fake path never reads the prompt.

**Effort: S.** One prompt rewrite in `domain_pack/analyze.py` + a test.

## Symptom
Of 8 agentic tool steps, **6 were wasted on tool calls that do not exist**:

```
TOOL add_asset    status=error  -> unknown tool add_asset     (x3)
TOOL create_page  status=error  -> unknown tool create_page   (x2)
TOOL web_search   status=error  -> unknown tool web_search    (x1)
```

The model's own finding recorded the confusion: *"Tools for create_page and add_asset are
returning errors. I can still use edit_content and change_design … The ingredients and meals
pages will need to be created in a subsequent run once the tool issue resolves."*

## Cost, measured in that run
- **No pages created** — the model wanted `ingredients.html` + `meals.html` and gave up on
  them after the tool calls failed.
- **No images added**, despite 4 *successful* `image_search` calls that returned licensed
  candidates. It found the images, then could not "call" `add_asset`.
- **Broken links shipped**: the `edit_content` that DID run wrote an `index.html` linking to
  the two pages that were never created. `broken_links` would score this — but nothing
  re-measures, see `run-on-internal-state.md`.
- Only 2 of the intended 4+ actions were proposed.

## Cause
`SYSTEM` in `domain_pack/analyze.py` renders the five actions in **call syntax**, in the same
register as the real tool descriptions that follow:

```
You may ONLY propose these actions: {actions}.
  create_page(target=relative/path.html, payload={content})   -- new page/file
  add_asset(target=assets/name.jpg, payload={url, license, ...}) -- download an image
  ...
Images: find them with image_search …, download them with add_asset, then …
Use the tools before proposing: ALWAYS read_page a file before edit_content …
```

`create_page(...)` is indistinguishable from `read_page(path)` to a model that has both a
tool-call channel and this text. "You may ONLY propose these actions" is one clause against a
whole block of function signatures and imperative verbs ("download them with add_asset").

The callable set is only `read_page` + whatever `_tools()` registers (`read_url`,
`image_search`, and `web_search` when a key exists) — nothing enforces or restates that split.

## Fix (proposed)
1. **Two visually distinct sections** with different syntax — never call-shaped for actions:
   - `TOOLS YOU CAN CALL NOW (read-only):` — the actual registered tool names, listed from
     `_tools(site)` so the prompt cannot drift from the offer.
   - `ACTIONS YOU CAN PROPOSE (returned as JSON at the end, NOT callable):` — describe them
     as JSON objects (`{"name": "create_page", "target": "...", "payload": {...}}`), which is
     the shape they must actually be emitted in, not as `f(a, b)`.
2. **Rewrite the imperative sentences** that read as tool instructions: "download them with
   add_asset" → "propose an `add_asset` action carrying the license fields verbatim".
3. **Only advertise available tools.** The prompt tells the model to "use web_search /
   read_url to research" even when no `TAVILY_API_KEY`/`EXA_API_KEY` makes `web_search`
   registrable — one of the six failed calls was exactly this. Build that sentence from the
   registered tool list.
4. *(built as the generic form: the error now names the callable tools, which proved enough —
   run-9d177565 and every run after it made zero phantom tool calls.)* Optional, cheap: make
   `run_tools` answer an unknown tool name that matches a known ACTION
   with a targeted message — `"create_page is an action, not a tool: return it in the actions
   array of your final JSON"` — instead of the generic `unknown tool`. The model self-corrects
   inside the same run rather than giving up.

## Test
Pack test with a scripted model that emits a `create_page` **tool call**: assert the run still
proposes `create_page` as an action (via the targeted error in (4)), and that the prompt built
by `analyze` lists no action name in its tools section.

## Minor, same run — split out to `backlog/metric-display-rounding.md`
- `goal_coverage` printed `1e-16` — the judge returned a tiny float instead of `0`. Clamping
  is correct (`max(0.0, min(10.0, …))`), it is only the display; round metric values for the
  CLI line.
