# Full RBAC & Data Governance

**What:** Role-based access control, data minimization, retention limits,
consent tracking (e.g. meeting recording), and per-source compliance policies.

**Why deferred:** Full governance is large and domain-specific (HR/finance/sales
each differ). v1 ships with a single read-only key (+ a TODO to scope it); proper
least-privilege, per-source scoping comes here.

**Value:** A single AI core with read access to everything is the highest-value
breach/surveillance target you can build. Governance makes broad capture safe.

**v1 seam (already in v1):** Connector credentials are read from config (not inline),
and the artifact schema is typed — so scoping, access rules, and retention can be
layered on per type/source later.

**First step:** scoped, read-only-by-default credentials per connector (no single
all-access key) — small effort once a second connector exists.

**Adds later:** roles & scopes, field-level redaction, retention/TTL on artifacts,
consent flags, audit-log export.

**Effort:** L
