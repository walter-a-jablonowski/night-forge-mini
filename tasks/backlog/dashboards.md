# Unified Cross-Domain Dashboards

**What:** Aggregate all domains (revenue, sales, engineering, hiring, ops…) into
custom real-time dashboards — the "queryable organization" view.

**Why deferred:** Only valuable once multiple specialized loops feed the store.
Large UI/aggregation effort; v1 is a single domain.

**Value:** Up-to-date, legible view of what's actually happening across the org.

**v1 preparation (already in v1):** Stable, typed, versioned artifact schema, with
every record tagged by `domain` (a constant in v1), means dashboards read existing
data and do cross-domain joins without backfills or schema changes.

**Adds later:** aggregation/query layer, visualizations, cross-domain joins,
natural-language query over the artifact store.

**Effort:** L
