# The model picks the wrong action for the target's state

**Found 2026-09-05**, website pack, run-393b4eee (`dots-studio/dots-3-note-preview:free`).
**3 of 5 proposed actions were refused** — every one of them for choosing an action whose
precondition the target did not meet:

```
create_page   index.html        -> FAILED  index.html exists; use edit_content
change_design ingredients.html  -> FAILED  invalid stylesheet path (.css only)
edit_content  snacks.html       -> FAILED  no such page 'snacks.html'; use create_page
```

**Effort: S.** A site-map rendering change in `analyze.py`, no new machinery.

**✅ RESOLVED 2026-09-05 — NO FIX NEEDED (self-corrected).** The "watch first" check below
came out in the design's favour: the very next pass (run-a257a9c6) saw the three refusals
through `history["failures"]` and got every action right — 5/5 ran, including the
`create_page snacks.html` that had been proposed as `edit_content` the run before. So this
is a one-run tax the closed loop already pays off, not a defect. Keep the site-map
annotation idea below only if a later run repeats the mistake AFTER seeing the feedback.

## The guards worked; the pass still mostly failed
This is not a safety hole — every refusal is the action protecting its own contract, nothing
wrong was written, the loop survived, and the refusals land in `history["failures"]` so the
next run sees them. That part of the design held up exactly as intended.

The cost is throughput: 60% of the proposals in that pass did nothing, and the run's stated
purpose — creating the missing `snacks.html` to fix a broken link — was the very action that
got refused (`edit_content` on a file that does not exist). The site was left broken.

## Cause
The prompt describes each action's precondition in prose:

```
{"name": "create_page",  ...}  -- new file (fails if it exists)
{"name": "edit_content", ...}  -- replace an existing page
{"name": "change_design","target": "path.css", ...}  -- write a stylesheet
```

and the SITE MAP lists what exists. So the information is all present, but it has to be
JOINED by the model: "is this path in the map? then not create_page". Under a long context
with many candidate improvements, that join is what slips — and it slips in both directions
at once, which is the tell that it is a lookup failure, not a misunderstanding of the actions.

## Fix
Render the applicable action INTO the site map, so no join is needed:

```
SITE MAP (existing files - use edit_content for pages, change_design for .css):
- index.html: NutriBowl (2103 chars)        [edit_content]
- style.css: (1804 chars)                   [change_design]
Anything NOT listed above does not exist yet -> create_page.
```

Plus one line in the action block: *"Check the site map first: a path that is listed exists
(never create_page it), a path that is not listed does not (never edit_content it)."*

## Do NOT auto-route
The tempting fix — silently turning `create_page` on an existing file into an
`edit_content` — must not happen. `create_page` is honestly `reversible: true` **because** it
refuses to overwrite; auto-routing would make a reversible, auto-running action destructive
behind the gate's back. The refusal is the contract. Same for `change_design`: its `.css`-only
rule is what earns it a separate line in the `allow_list`.

## Watch first
The failures feed back through `history["failures"]`, so the designed self-correction may
already handle this on the next pass. Check a follow-up run before spending effort: if the
model stops repeating the mistake once it sees the refusals, this is a one-run tax, not a bug.
