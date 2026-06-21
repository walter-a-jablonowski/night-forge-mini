# Library / Embedded Use — call the engine in-process

**What:** Invoke the system programmatically instead of via the CLI:
```python
from night_forge_mini.config import load
from night_forge_mini.loop import Engine
import domain_pack

cfg = load("config.json")
eng = Engine(cfg, domain_pack.build_pack(cfg), fake_llm=True)
eng.run_once(); eng.approve(action_id)
```

**Status:** **already works today** — the CLI is just one caller of `Engine`. This item is
mostly **documenting + lightly hardening** it as a supported entry point (tests, notebooks,
embedding the loop inside a larger app or another agent).

**Value:** Lowest-friction integration: scripting, automated tests/CI, notebooks, and using
the loop as a component without shelling out to the CLI.

**v1 seam (already in v1):** `Engine.run_once()/approve()/reject()` + the `Store` read methods
are the same surface the CLI uses. Nothing to build to *call* it.

**Adds later:** a tiny documented facade (stable public functions), typed return objects
instead of dicts, and a usage section in `blank/README.md`. Pairs with
[http-api-server.md](http-api-server.md) (the out-of-process equivalent).

**Effort:** XS (document) → S (stable facade + typed returns)
