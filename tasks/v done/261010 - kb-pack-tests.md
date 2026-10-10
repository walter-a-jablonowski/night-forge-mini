# kb pack has no tests

**DONE 2026-10-10.** `domains/kb/tests/test_kb_pack.py`, 6 tests, all five scope rows plus
the gate's hard floor on this pack (edit_entry allow-listed but held without git). Verified
by mutation: reverting the §5 header in `kb/domain_pack/analyze.py` fails the age test.
The pack loads as `kb_domain_pack` (see `tests/conftest.py`): the documented command
collects both domains in one session and both packs are named `domain_pack`, so a plain
import would have silently tested the website pack twice. Test command in `CLAUDE.md`
updated. 167 -> 173 tests.

**Size: S.** `domains/kb/` ships `config.json`, `data/`, `domain_pack/`, `README.md` — and
no `tests/`. The website pack has 40+.

## Why it surfaced

The long run's §5 fix (findings rendered with an age, so a solved problem is not re-solved)
was applied to **both** packs — the kb pack carried the identical bare `RECENT FINDINGS:`
line. Only the website half has a test:

```
domains/website/tests/test_analyze_prompt.py:102   assert '3 runs ago' in user
domains/kb/    (nothing)
```

A copy-paste fix with a test on one side only is the shape that regresses quietly: the next
person edits `_render_context` in the kb pack, the suite stays green.

## What it is not

Not "raise kb coverage to N%". The pack is a **reference implementation of the `Pack` seam**
— its job is to prove the seam works for something other than the website. The tests should
say that, and nothing more.

## Scope

| test | why |
|---|---|
| `_render_context` renders ages + the AS-IT-WAS header | the §5 fix, currently unguarded |
| `_relevant_slice` caps context and is stable on ties | the only non-trivial logic here |
| `_stamp_edit_base` fingerprints proposed `edit_entry` | the stale-edit guard's own input |
| `tools_for(kb)` is non-empty | an agent backend with no tools invents answers |
| one `--fake-llm` pass end to end | the seam contract itself |

Last item earns the most: it is the check that the core still runs a second pack at all.

## Notes

- the website pack's `tests/` is the pattern to follow — same layout, same naming
- add `domains/kb/tests` to the command in `CLAUDE.md` once it exists
