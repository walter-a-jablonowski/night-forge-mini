# Run triggers / invocation methods

Alternative ways to **invoke** the system beyond single CLI commands. Each file is one
method. They are all *additive*: a trigger is just another **caller of `Engine.run_once()`**,
and an approval channel is just another **caller of `decide()`** — no core rewrite.

idea_2 deferred "cron/daemon"; none of these are built yet. One pass = one `run_once()`
(capture→analyze→propose→gate); these files are only about *what fires that pass and how
you talk to it*, not the loop logic.

## Files (by effort)
- [scheduler-daemon.md](scheduler-daemon.md) — interval poll loop (the realistic "endless loop"). **S**
- [filesystem-watch.md](filesystem-watch.md) — fire a run when a new artifact lands (event-driven). **S**
- [library-embed.md](library-embed.md) — call the engine as a Python library (already works; document + harden). **XS**
- [http-api-server.md](http-api-server.md) — HTTP endpoints over the engine; substrate for UI/remote/webhooks. **M**
- [webhook-trigger.md](webhook-trigger.md) — inbound webhook fires a run (builds on the API server). **M**

## Shared safety note (read before any *unattended* method)
A non-interactive trigger (daemon, watcher, webhook) changes the risk profile:
allow-listed actions auto-run with **no human watching**, and held/`pending` actions **pile
up unseen**. Any unattended trigger therefore needs:
1. a **notification/escalation path** for pending actions (Slack/email/the `approval-ui` inbox), and
2. trust in the `allow_list` (default-deny still holds; see `../autonomous-actions.md`).

Don't ship a silent unattended trigger without (1) — that's how the loop quietly stalls on
a pending action or auto-amplifies a bad proposal. Approval *channels* (Slack/email/web
approvers) live in `../approval-ui.md`.
