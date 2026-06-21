# NightForge mini 1 — Self-improving Knowledge Base (v1)

A minimal, working implementation of [idea_2.md](../idea_2.md): one hardcoded domain
(curating a markdown knowledge base from incoming text), the full closed loop, an
append-only JSONL artifact store, and a per-action approval gate with a **reversible
hard floor**.

## How it maps to the spec

| idea_2 concept | Code |
|---|---|
| Append-only log = source of truth | `skb/store.py` (JSONL), `skb/data/log.jsonl` |
| Typed record + closed `type` enum | `skb/records.py` |
| Connector `fetch() -> artifacts` | `skb/connector.py` (`text-folder`) |
| Goal/metric/allow-list as **data** | `skb/config.json` + `skb/config.py` |
| Analysis = swappable function | `skb/analyze.py` |
| Action `{name, risk_level, reversible, run}` | `skb/actions.py` |
| Gate (allow-list **and** reversible) + `decide()` | `skb/gate.py` |
| One model-call wrapper (provider switch / observability seam) | `skb/llm.py` |
| Loop + resume (approve/reject under original run_id) | `skb/loop.py` |
| CLI over the log | `skb/cli.py` |

### The gate, concretely

Auto-run requires **both** `name in allow_list` **and** `reversible == true`.
- `add_entry`, `flag_contradiction`, `mark_stale` → reversible, allow-listed → **auto-run**.
- `edit_entry` overwrites curated content → `reversible == false` → **always held** (hard floor; a mis-config can't auto-run it).

The markdown files under `skb/data/kb/` are the **materialized artifact**; every change is
also recorded in the JSONL log, which stays the source of truth.

## Using a real model

Providers are config-driven and OpenAI-compatible (`skb/config.json` → `providers`):

- `openrouter` (default) — set `OPENROUTER_API_KEY`. Confirm the exact model slug for
  Gemini 3 Flash preview on OpenRouter and put it in `providers.openrouter.model`.
- `gemini` — set `GEMINI_API_KEY` (Google OpenAI-compatible endpoint).
- `ollama` — local, no key needed (default dummy key).

Keys load from a `.env` in the project root (copy `.env.example` → `.env`).
Switch provider with `"provider": "<name>"` in `skb/config.json`, then:

```bash
cp .env.example .env        # fill in your key
pip install -r requirements.txt
python -m skb run-once
```

## Data layout

```
skb/                         self-contained implementation
├─ config.json               domain, goal, metric, allow-list, providers, paths
├─ data/inbox/               incoming text snippets (the one connector's source)
├─ data/kb/                  materialized markdown knowledge base (output)
└─ data/log.jsonl            append-only artifact store (source of truth)
.env                         provider API keys (git-ignored; template is .env.example)
```
Run from the project root (`python -m skb …`); the default `--config skb/config.json`
resolves `data/` inside `skb/`, so the whole implementation is self-contained — a future
version regenerated from `idea_2.md` can live in a sibling folder without collision.

## Missing in v1 (see tasks/backlog/)

Registry/multi-domain, RBAC, cost/ROI, observability tooling, drift detection,
dashboards, software factory, approval UI, multi-channel capture — each has a seam here
so it can be added without a core rewrite.
