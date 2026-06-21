# HTTP / API Server — endpoints over the engine

**What:** A small HTTP service exposing the five operations — `POST /run-once`, `GET /inbox`,
`POST /approve/{action_id}`, `POST /reject/{action_id}`, `GET /trace/{run_id}`. Thin handlers
that call `Engine` / `decide()` and return JSON.

**Why deferred:** A server is a real new component against v1's "runs locally, single file, no
server" floor. The CLI is enough to operate the loop. Build it when remote/multi-user/automated
access is actually needed.

**Value:** The **shared substrate** for several other methods: a web approval UI, remote and
multi-user access, programmatic integration over the network, and inbound
[webhook triggers](webhook-trigger.md). Build once, unlock all of them.

**v1 seam (already in v1):** the log *is* the state and every operation already goes through
`Engine` / the one `decide(action_id, verdict, edits?)` — so each endpoint is a new caller, not
a reimplementation of the loop or the gate. A Slack/API approver is the same seam.

**Adds later:** auth + RBAC (pairs with `../data-governance.md`), the web inbox/diff view
(`../approval-ui.md`), an SSE/stream for live run output, OpenAPI schema.

**Safety:** exposing `run-once`/approve over the network = unattended + remote; needs auth and
the pending-notification path — see [README.md](README.md).

**Effort:** M
