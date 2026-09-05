# A write action accepts content of the wrong shape for the file

**Found 2026-09-05**, website pack, run-393b4eee. `edit_content style.css` wrote a **complete
HTML page** into the stylesheet — `<!DOCTYPE html>`, `<head>`, a `<title>NutriBowl…`, even a
`<link rel="stylesheet" href="style.css">` pointing back at the file it was overwriting.
81 lines of HTML in the site's only `.css`.

```
$ git show 8f15ea4:style.css | head -3
<!DOCTYPE html>
<html lang="en">
<head>
```

**Effort: S.** A shape floor in `constraints.py`, next to the existing hotlink floor.

## Why it matters more than it looks
- **Nothing refused it.** Not the gate (`edit_content` is allow-listed and git-recoverable),
  not `HardConstraints` — `check_css` only looks for forbidden colors, and this payload had
  none. Every guard the pack has was satisfied by a stylesheet full of HTML.
- **No metric noticed.** `pages`, `broken_links` and `seo_basics` all stayed green across the
  whole window: the pages were present, their links resolved, their titles and meta
  descriptions were intact. The site was completely unstyled and every number said fine.
- **It survived a full run cycle.** The broken stylesheet was committed by run-393b4eee and
  only replaced by run-a257a9c6, one whole pass later.
- **Recovery was luck, not design.** The next run happened to notice ("style.css contained
  HTML instead of CSS") and fixed it. Nothing in the system would have escalated if it
  hadn't — compare `website-action-precondition-confusion.md`, where the refusals fed back
  through `history["failures"]` and the loop provably self-corrected. Here there was no
  refusal to feed back.

## Cause
Both stylesheet paths check content only for brand policy:

| write | target rule | content rule |
|---|---|---|
| `edit_content` | file must exist | `check_page` (or `check_css` since the suffix fix) |
| `change_design` | `.css` only | `check_css` — forbidden colors |

`change_design` constrains the *path* to `.css` but never asks whether the *payload* is CSS.
So "is this a stylesheet?" is enforced on the filename and nowhere else.

## Fix
A shape floor in `HardConstraints`, active with no config — the same standing as
`allow_hotlinking`, and reached through the `check(target, …)` router that already picks
rules by suffix:

- **`.css` payload** — refuse when it opens with `<!DOCTYPE`/`<html` or contains `</html>`.
  Deliberately narrow: CSS may legitimately contain `<` inside a `content:` string, so test
  for document structure, not for angle brackets.
- **`.html` payload** — refuse when it contains no tag at all (the inverse mistake: a
  stylesheet written into a page).

Put it in `constraints.py` rather than `Site`: `Site` owns paths and bytes, and this is a
statement about acceptable content, which is exactly what that module already decides. It is
a floor, not an operator setting — there is no sane deployment that wants HTML in its CSS.

## Secondary option (cheaper, weaker)
A `styles_ok` metric module that scores stylesheets that parse as CSS. It would have made the
damage *visible* in the metric line, but only after the fact — a refusal prevents the bad
write, a metric merely reports it. Worth adding as well, not instead.

## Test
Table-driven over `create_page` / `edit_content` / `change_design`: an HTML document refused
for a `.css` target through every one of them, real CSS accepted, and a `content: "<b>"`
declaration accepted (the false-positive guard).
