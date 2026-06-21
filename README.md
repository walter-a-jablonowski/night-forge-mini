# NightForge mini — self-improving closed-loop system

A minimal, working implementation of [idea_2.md](idea_2.md): the closed loop
(capture → ingest → analyze → propose → gate → improve) over an append-only JSONL
artifact store, with a per-action approval gate and a **reversible hard floor**.

It is built as a **blank, domain-agnostic core** plus exactly one pluggable **domain
pack**. The core has no use case of its own — you drop in a pack and deploy. The included
demo pack curates a markdown knowledge base from incoming text snippets.

## Repo layout

```
blank/                 reusable core — see blank/README.md
├─ night_forge_mini/   the engine (loop, store, gate, records, llm + the pack seam)
└─ config.example.json · .env.example · requirements.txt
domains/kb/            demo domain pack — see domains/kb/README.md
├─ domain_pack/        connector, actions, analysis  (build_pack(cfg) -> Pack)
├─ config.json         ready-to-run deploy config
└─ data/inbox/         six demo snippets
idea_2.md              the spec this implements
tasks/                 working notes + tasks/backlog/ (deferred features)
```

**Deploy** = duplicate `blank/`, copy the *contents* of a domain (e.g. `domains/kb/`) into
it, then `python -m night_forge_mini run-once`. Step-by-step instructions live in
[blank/README.md](blank/README.md) and [domains/kb/README.md](domains/kb/README.md).
Add `--fake-llm` to run the whole loop offline with no API key or tokens.

## How it maps to the spec

The core (`blank/night_forge_mini/`) is domain-agnostic; the pack
(`domains/kb/domain_pack/`) supplies the domain.

| idea_2 concept | Code |
|---|---|
| Append-only log = source of truth | core `store.py` (JSONL) |
| Typed record + closed `type` enum | core `records.py` |
| Loop + resume (approve/reject under original `run_id`) | core `loop.py` |
| Gate (allow-list **and** reversible) + `decide()` | core `gate.py` |
| One model-call wrapper (provider switch / observability seam) | core `llm.py` |
| CLI over the log | core `cli.py` |
| The pack seam — `Connector` / `Action` / `Pack` | core `pack.py` |
| Connector `fetch() -> artifacts` | pack `connector.py` (`text-folder`) |
| Analysis = swappable function (also measures the metric) | pack `analyze.py` |
| Action `{name, risk_level, reversible, run}` | pack `actions.py` |
| Goal + metric (pack-owned) · allow-list (deploy config) | pack code + `config.json` |

### The gate, concretely

Auto-run requires **both** `name in allow_list` **and** `reversible == true`; otherwise the
action is held for human approval. The `reversible == false` block is a hard floor enforced
in code — a mis-configured allow-list still cannot auto-run an irreversible action.

In the KB demo pack:
- `add_entry` (create-only), `flag_contradiction`, `mark_stale` → reversible, allow-listed → **auto-run**.
- `edit_entry` overwrites curated content → `reversible == false` → **always held** for approval.
- `add_entry` refuses to overwrite an existing entry — that refusal is what keeps its
  `reversible: true` honest; changing an entry must go through `edit_entry` (which needs approval).

The markdown files under `data/kb/` are the **materialized artifact**; every change is also
recorded in the JSONL log, which stays the source of truth.

## Using a real model

Providers are config-driven and OpenAI-compatible (`config.json` → `providers`):

- `openrouter` (default) — set `OPENROUTER_API_KEY`.
- `gemini` — set `GEMINI_API_KEY` (Google's OpenAI-compatible endpoint).
- `ollama` — local, no key needed (default dummy key).

Keys load from a `.env` in the run directory (copy `.env.example` → `.env`). Switch provider
with `"provider": "<name>"` in `config.json`, then:

```bash
cp .env.example .env        # fill in your key
pip install -r requirements.txt
python -m night_forge_mini run-once
```

## Deferred (see tasks/backlog/)

Multi-pack registry / auto-discovery (the single-pack split is done), RBAC & governance,
cost/ROI, observability tooling, drift detection, trusted autonomy, dashboards, software
factory, approval UI, multi-channel capture, and bounded retrieval — each has a seam here so
it can be added without a core rewrite.
