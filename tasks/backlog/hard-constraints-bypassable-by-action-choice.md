# Hard constraints are bypassable by choosing a different action

**Found 2026-09-04**, website pack, second real-model run (run-9d177565). The model wrote
`style.css` with `edit_content` instead of `change_design` — and `edit_content` never runs the
CSS checks. A "hard" constraint that a model can route around is a soft one.

**Effort: XS–S.** Dispatch the check by what the FILE is, not by which action was named.

**✅ DONE 2026-09-04.** `HardConstraints.check(target, content, previous=)` is now the single
entry point and routes by suffix; `create_page` / `edit_content` / `change_design` all call it
(`site.py`). `check_page` additionally runs the CSS rules over a page's `<style>` blocks and
`style=""` attributes, so inlining is not an escape either — prose is untouched, a page may
still say "blue cheese". 4 tests written failing first, then fixed; 104 pass. Verified live in
`try/website/` (run-b1e9637c: 4 writes, no false refusals).

## Reproduced
```python
site = Site(d, hard=HardConstraints(forbidden_colors=['blue', '#0000ff']))
bad = 'body { color: blue; background: #0000ff; }'

site.change_design('style.css', {'content': bad})
# -> {'status': 'error', 'detail': "refused: forbidden color(s) blue, #0000ff …"}

site.edit_content('style.css', {'content': bad})
# -> {'status': 'ok', 'detail': 'edited style.css'}      <-- written, colors and all
```

The run that exposed it was not adversarial: `edit_content` on an existing `.css` is a
perfectly natural reading of "replace an existing page's source", and the model took it.

## Cause
The checks are bound to the ACTION, not to the CONTENT (`domain_pack/site.py`):

| action | check called | covers |
|---|---|---|
| `create_page` | `check_page` (site.py:157) | required_snippets, hotlinking |
| `edit_content` | `check_page` (site.py:176) | required_snippets, hotlinking |
| `change_design` | `check_css` (site.py:195) | **forbidden_colors** |

`change_design` restricts its own target to `.css`, but nothing stops `edit_content` from
writing one — so `forbidden_colors` is enforced on exactly one of the two paths that can
produce a stylesheet. The same hole runs the other way in principle: a `.html` file written
through `change_design` would skip `check_page`, though the `.css`-only guard blocks that today.

## Fix
Pick the check from the target's suffix inside a single private helper both writes call:

```python
def _check(self, target: str, content: str, previous: str | None = None) -> str | None:
  if target.endswith('.css'):
    return self.hard.check_css(content)
  return self.hard.check_page(content, previous=previous)
```

Then `create_page`, `edit_content` and `change_design` all call `self._check(...)` and the
constraint follows the file, which is what "hard constraint" has to mean. Keep
`change_design`'s `.css`-only target rule — that is a policy about the action, and it is fine
for a policy to be per-action; what must not be per-action is the *content* rule.

Consider also running `check_css` on `<style>` blocks inside a page, otherwise the same
forbidden color is reachable by inlining it in HTML.

## Test
Table-driven over the three writes: for each, a forbidden color in a `.css` target must be
refused and the file left unchanged; `required_snippets` / hotlinking must still be enforced
on `.html` targets through all of them.
