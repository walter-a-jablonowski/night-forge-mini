# Trusted Autonomy (beyond the static allow-list)

**What:** Move from v1's hand-curated allow-list toward *earned* autonomy — the agent
decides what's safe to run via a risk classifier, with rollback to make it safe.

**Already in v1:** Scoped autonomy via a **static, config allow-list** — allow-listed
(low-risk/reversible) actions auto-run; everything else holds for human approval;
default-deny. Every action carries `risk_level` **and a `reversible` flag** and flows
through the one gate — so a later autonomy policy + rollback can key off both without
changing the action shape.

**Why the rest is deferred:** Dynamic trust requires a classifier you can rely on and
a rollback mechanism. Premature autonomy removes the people who'd catch a wrong
"probabilistic" output — so v1 keeps the allow-list human-curated and static.

**Value:** Throughput on safe, repetitive actions without a human curating every
allow-list entry by hand.

**Adds later:** risk classifier (replaces the static list), reversibility/rollback per
action type, per-action-type autonomy policy, post-hoc review sampling.

**Effort:** M
