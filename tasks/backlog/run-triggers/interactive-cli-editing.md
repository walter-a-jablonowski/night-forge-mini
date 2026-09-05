# REPL: edit-before-approve + streaming output

Split out of `run-triggers/interactive-cli.md` (S done 2026-06-21, see `tasks/v done/`), which
shipped the REPL and left this M-sized half.

**Effort: M.**

## What is missing
The REPL loads engine + pack + config once and loops on `nfm> ` with `run`, `inbox`,
`approve <id|n>`, `reject <id|n>`, `trace <run_id>`. Approval is all-or-nothing: you take the
proposed action exactly as the model wrote it, or you reject it.

1. **Edit before approving.** Open a held action's payload, change it, then approve the edited
   version. `Engine.approve(action_id, edits=...)` already accepts edits — the seam exists; the
   REPL has no way to produce them. This matters most for the website pack, where a held
   `edit_content` carries a whole file body.
2. **Streaming.** A run currently prints nothing until it finishes. With agentic analyze that
   is minutes of silence — tool calls and the finding should appear as they happen.

## Notes
- Streaming needs a callback seam through `ModelWrapper`, which is also where a tracer would
  hook in (`observability.md`) — worth designing the two together rather than twice.
- Edit-before-approve overlaps `approval-ui.md`: the same diff-and-edit problem, one in the
  terminal and one in a browser. Decide which surface is primary before building both.
- `stale-edit-guard` already protects an edited approval from clobbering an intervening
  change, so the risky half of this is done.
