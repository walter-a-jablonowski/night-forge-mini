"""night_forge_mini — the blank, domain-agnostic core of the self-improving
closed-loop system.

This package has **no use case** on its own. It defines the loop runner, the
append-only artifact store, the approval gate, the record schema, and the model
wrapper — plus the `pack.py` seam. A deployment plugs in exactly one **domain pack**
(a `domain_pack` package providing `build_pack(cfg) -> Pack`) and runs.

See tasks/blank-core-and-domain-pack.md and tasks/backlog/domain-pack-template.md.
"""

SCHEMA_V = 1
