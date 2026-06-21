# Plan: Blank Core + Pluggable Domain Pack

**Goal:** split the working `skb/` system into a reusable **blank core** (no use case) and a
**domain pack** (exactly one domain), so a deployment = duplicate the core + drop in one pack.
This is *not* a runtime registry of many packs — it's one pack per deployment. Based on
`tasks/backlog/domain-pack-template.md` (the "four things" a pack provides), simplified: no
registry/auto-discovery, just a fixed `import domain_pack` seam.

`skb/` stays untouched as the reference implementation. We build `blank/` + `domains/kb/` fresh
and verify them independently.

---

## Deploy workflow this enables
1. **Duplicate `/blank`** → `my-system/`
2. **Copy the *contents* of `/domains/kb`** into `my-system/` (lands `domain_pack/`, `config.json`,
   `data/`, `README` at the root next to `night_forge_mini/`)
3. **Run** `python -m night_forge_mini run-once`

`/blank` alone is intentionally **not runnable** (no use case). Running it prints a friendly
message: *"No domain_pack found — copy a domain from /domains into this folder."*

---

## Target repo structure (new, alongside the existing `skb/`)
```
blank/
├─ night_forge_mini/        # CORE package — pure, domain-agnostic
│  ├─ __init__.py           # SCHEMA_V
│  ├─ pack.py               # NEW: Connector / Action / Pack interfaces (the seam)
│  ├─ records.py            # = skb (unchanged)
│  ├─ store.py              # = skb — KEEPS round-5 fixes (tolerant read + newline guard)
│  ├─ gate.py               # REFACTORED: drives pack.actions, not KnowledgeBase
│  ├─ loop.py               # REFACTORED: Engine takes a Pack; loads `import domain_pack`
│  ├─ llm.py                # = skb (unchanged)
│  ├─ config.py             # trimmed: infra only (provider/paths/allow_list/recent_runs/connector params)
│  ├─ env.py                # = skb (unchanged)
│  ├─ cli.py                # = skb, minus KB-specific wording — KEEPS round-3 honest reporting
│  └─ __main__.py           # = skb
├─ config.example.json      # infra template (no goal/metric)
├─ .env.example
├─ requirements.txt
└─ README.md                # "the engine + how to plug a pack"

domains/kb/
├─ domain_pack/             # PACK package — fixed import name
│  ├─ __init__.py           # exposes build_pack(cfg) -> Pack
│  ├─ connector.py          # TextFolderConnector (moved out of core)
│  ├─ actions.py            # KnowledgeBase + ACTIONS — KEEPS round-2 create-only
│  └─ analyze.py            # analyze() now also measures the metric — KEEPS round-4 tolerant _normalize
├─ config.json              # ready-to-run: infra defaults + kb allow_list + connector source
├─ data/inbox/*.md          # the 6 demo snippets (copied from skb/data/inbox)
└─ README.md                # "what the KB domain does"
```

---

## The seam — `night_forge_mini/pack.py` (new)
```python
class Connector(Protocol):
    name: str
    def fetch(self, seen_ids: set[str]) -> list[dict]: ...

@dataclass
class Action:
    name: str
    risk_level: str
    reversible: bool
    run: Callable[[str, dict], dict]      # (target, payload) -> {status, detail}

@dataclass
class Pack:
    domain: str
    goal: str
    connector: Connector
    actions: dict[str, Action]
    analyze: Callable[..., dict]          # -> {finding, metric, actions}
```
**Registration contract:** a domain is a folder providing a `domain_pack` package that exposes
`build_pack(cfg) -> Pack`. Core does `import domain_pack; pack = domain_pack.build_pack(cfg)`.

---

## The three decouplings (core stops importing KB concretes)
1. **`gate.py`** — drop `from .actions import ACTIONS, KnowledgeBase`.
   - `decide(store, actions, *, domain, run_id, action, verdict, by, edits=None)` calls
     `actions[name].run(target, payload)`, still wrapped in the round-1 try/except → `error` outcome.
   - `can_auto_run(name, allow_list, actions)` reads `actions[name].reversible` (hard floor preserved).
   - `domain` is passed in from the pack — no more hardcoded `"knowledge-base"`.
2. **`loop.py`** — `Engine(cfg, pack, fake_llm)`. Uses `pack.connector`, `pack.analyze(...)`,
   `pack.actions`. The `import domain_pack` + `build_pack(cfg)` happens at the CLI/`__main__` entry,
   with a friendly error if the pack is absent.
3. **`connector.py`** — the `Connector` **Protocol** moves into `night_forge_mini/pack.py`;
   `TextFolderConnector` + its `build` move into `domain_pack/connector.py`.

---

## Metric & ingest move into the pack (resolves the old "B")
`pack.analyze(model, goal, snippets, recent_findings, store)` returns `{finding, metric, actions}`.
The KB pack measures `kb_entries`/`stale` and builds its own `kb_index` **inside** analyze. The core
just **records** whatever metric the pack returns. Consequences:
- The metric definition + measurement become **pack-owned** (fixes the old dead `config.metric`).
- `connector.source` stops being dead config — the pack reads it when wiring its connector.

---

## Config split (ownership)
- **Pack code owns:** goal, metric (definition + measurement), connector impl, actions
  (+ honest `reversible` / `risk_level`).
- **`config.json` (deploy root) owns:** `provider` / `providers`, `paths`, connector
  **params/creds** (`source`), **`allow_list`** (the operator's auto-run policy), `recent_runs`.
- `blank/config.example.json` documents the infra fields (no goal/metric).
  `domains/kb/config.json` is the complete ready-to-run file (KB ships a sensible `allow_list`
  default the operator can edit). The pack declares each action's honest reversibility; the
  operator's `allow_list` decides what may auto-run here.

---

## What carries over unchanged (all five hardening fixes survive the move)
| Fix (round) | Lands in |
|---|---|
| Action exception → `error` outcome (R1) | core `gate.py` |
| `add_entry` create-only (R2) | pack `actions.py` |
| CLI honest auto-run / approve reporting (R3) | core `cli.py` |
| Tolerant `_normalize` for malformed model output (R4) | pack `analyze.py` |
| Store tolerant read + torn-tail newline guard (R5) | core `store.py` |

---

## Naming decisions
- Core package: **`night_forge_mini`** (the project name `night-forge-mini` with underscores,
  since hyphens aren't valid in Python import names); entry point `python -m night_forge_mini`.
- Pack package (fixed import name): **`domain_pack`**.
- Repo holds domains under `domains/<use_case>/` (e.g. `domains/kb/`); the importable package
  inside each is always `domain_pack/`.

---

## Verification (executed in implement step)
1. Merge into a temp dir (`blank/*` + `domains/kb/*`), set `PYTHONPATH`, then `--fake-llm`:
   - `python -m night_forge_mini run-once`: capture → analyze (finding + metric) → auto-run; confirm honest `AUTO-RAN ok/FAILED`.
   - pending → `inbox` → `approve` → `trace`: one coherent tree under the original `run_id`.
   - `reject` + double-decide guards.
2. Re-confirm the five hardening behaviors in the new layout (create-only refusal, torn-line
   survival, malformed-output tolerance, failure→error outcome).
3. Confirm `/blank` alone prints the friendly "no domain_pack" message and does not crash.

---

## Out of scope (unchanged from idea_2 deferrals)
Multi-pack registry/auto-discovery, cost/ROI, observability, drift detection, dashboards,
multi-channel capture, approval UI, trusted autonomy beyond the static allow-list. The
bounded-context "relevant slice" (KB index still loads fully) stays a v1-acceptable simplification.
