# Webhook Trigger — external event fires a run

**What:** Let an external system start a pass by calling in: a webhook endpoint (e.g.
`POST /hooks/<source>`) that an upstream service (GitHub, Slack, Linear, a form, a cron-as-a-
service) hits when something happens → the handler calls `run_once()` (optionally passing the
event payload to the connector).

**Why deferred:** Needs the [http-api-server.md](http-api-server.md) substrate first, plus
per-source payload handling and signature verification. v1 has no inbound surface.

**Value:** True push-based, cross-system triggering — the loop reacts to real org events
instead of polling. This is the realistic version of "agents in all channels" for *triggering*
(capture of those channels' content is `../multi-channel-capture.md`).

**v1 seam (already in v1):** triggering is just `run_once()`; the connector already owns "what's
new" via log-derived dedup. A webhook is a thin authenticated caller. Per-connector: the source
must be able to push (or a proxy pushes for it).

**Adds later:** signature/secret verification per source, payload → connector mapping, dedup of
duplicate deliveries, rate limiting. Builds directly on the API server's auth.

**Safety:** inbound + unattended; verify signatures, and keep the pending-notification +
allow-list trust from [README.md](README.md).

**Effort:** M (on top of [http-api-server.md](http-api-server.md))
