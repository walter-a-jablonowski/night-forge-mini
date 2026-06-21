# Domain pack: knowledge-base

Curates a knowledge base of markdown entries from incoming text snippets. This is the
worked example for the `night_forge_mini` blank core.

## What it does
- **Connector** `text-folder` — reads `.md`/`.txt` snippets from `data/inbox/`.
- **Goal** — maintain a complete, non-redundant, current KB.
- **Metric** (measured each run, in `analyze`) — `kb_entries`, `stale`, `incoming_new`.
- **Actions** — `add_entry` (create-only, reversible), `flag_contradiction`, `mark_stale`
  (reversible) and `edit_entry` (NOT reversible → always held for approval). The materialized
  KB is written as markdown files under `data/kb/`.

## Deploy
Copy the **contents** of this folder into a duplicate of `blank/`, so it looks like:
```
my-system/
├─ night_forge_mini/   (from blank/)
├─ domain_pack/        (from here)
├─ config.json         (from here)
├─ data/inbox/*.md     (demo snippets, from here)
├─ .env                (cp from .env.example, add your key)
└─ requirements.txt
```
Then:
```
python -m night_forge_mini --fake-llm run-once   # offline demo, no key needed
python -m night_forge_mini run-once              # real model (needs a provider key)
python -m night_forge_mini inbox
python -m night_forge_mini approve <action_id>
python -m night_forge_mini trace <run_id>
```

## Files
- `domain_pack/__init__.py` — `build_pack(cfg) -> Pack` (the wiring).
- `domain_pack/connector.py` — `TextFolderConnector`.
- `domain_pack/actions.py` — `KnowledgeBase` + action metadata + `build_actions`.
- `domain_pack/analyze.py` — analysis strategy + metric measurement.
- `config.json` — ready-to-run deploy config (provider, paths, connector source, allow_list).
- `data/inbox/` — six demo snippets to ingest.
