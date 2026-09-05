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

**✅ DONE 2026-09-05.** Implemented as specified below — a floor in `HardConstraints`,
reached through the `check(target, ...)` suffix router, so all three writes enforce it.
- `.css`: refused when the payload opens with `<!DOCTYPE html` / `<html` or contains
  `</html>` — document structure, not angle brackets.
- pages: refused when the payload contains no markup at all. The pattern accepts `<?`,
  so a pure-PHP `.php` page (PAGES includes .php) is not mistaken for a stylesheet.
- Verified against the REAL payload from git (`8f15ea4:style.css`, 82 lines): refused as
  `.css`, while the repaired stylesheet passes, the same bytes as a PAGE pass (no false
  positive), and the real CSS written into a page is caught.
- `check()` now routes by EXPLICIT suffix sets (`STYLE_SUFFIXES` / `PAGE_SUFFIXES`) instead
  of treating every non-`.css` target as a page. Running the floor over the live site
  caught this: an asset's `.license.txt` sidecar was being judged by the markup rule.
  Unreachable through the write actions (`safe_path` refuses such targets), but the
  default-to-page branch was a trap waiting for the first text asset.
- 6 tests, written failing first; 120 pass. Re-verified over every file of the live
  `try/website/` site: all ok, no false positives.

The `styles_ok` metric was NOT built — the refusal prevents the write, which was the point.
It is split out as its own item: `backlog/styles-ok-metric.md`.

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

## Secondary option (not built — moved to `backlog/styles-ok-metric.md`)
A `styles_ok` metric module would have made the damage *visible* in the metric line, but only
after the fact — a refusal prevents the bad write, a metric merely reports it. Worth adding as
well, not instead, so it survives as its own backlog item.

## Test
Table-driven over `create_page` / `edit_content` / `change_design`: an HTML document refused
for a `.css` target through every one of them, real CSS accepted, and a `content: "<b>"`
declaration accepted (the false-positive guard).
