# Multi-Channel Capture

**What:** Broaden capture so every important action becomes an artifact: AI
notetaker for meetings, agents embedded in all comms channels, minimizing
ephemeral DMs/emails.

**Why deferred:** Many integrations + consent/recording concerns. v1 starts with
1–2 connectors to prove the loop.

**Value:** The richer the artifact stream, the better the loop learns — this is
what makes the org "legible to AI."

**v1 preparation (already in v1):** Connector interface (`fetch() -> artifacts`) is
pluggable, so each new channel is a new connector, not a core change. Pairs with
[data-governance.md](data-governance.md) for consent/retention.

**Adds later:** meeting notetaker, per-channel agents, email/DM ingestion.

**Effort:** L
