# kb: an edit must record where its content came from

**DONE 2026-10-11.** Found live on `try/kb`: an MFA note merged into `vpn-setup` by
`edit_entry`, and the entry's `source:` still named only the two snippets that created it.
The trail existed in the log (run -> input snippet ids) and in git (commit names the run),
but the entry itself could not say where its latest content came from.

| piece | where |
|---|---|
| `edit_entry` merges `payload.source` into the entry's list (order kept, no repeats); no source = list unchanged | `domains/kb/domain_pack/actions.py` |
| `_sources()`: one parser for string or list; `add_entry` uses it too (a list used to be written as a Python literal) | same |
| prompt: `edit_entry(payload={body, source})`, and what `source` means | `domains/kb/domain_pack/analyze.py` |
| fake edit carries a source, like the fake add | same |

Tests: `test_an_edit_adds_its_snippets_to_the_entrys_sources`,
`test_a_list_source_is_written_as_the_frontmatter_list` — both fail without the fix.

Live 2026-10-11: an on-call note edited `oncall-rotation`; `source:` went from 2 to 3 ids,
and the new one is the snippet id the run actually captured (checked against the log's
input record), not an invented one.

Not done: entries edited before the fix keep their incomplete list (scratch deploy only).
