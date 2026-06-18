# Approval Review UI

**What:** A small local web view over the artifact log for reviewing and acting on
`pending` actions — list the inbox, read each action + its proposal/analysis/trace
context, edit the proposed action, then approve / reject (per action) in one click.
Optionally render the run's hierarchical trace as a tree.

**Why deferred:** A server + frontend are real new components, against v1's
"runs locally, single file, no server" floor. v1's CLI (`inbox` / `approve` /
`reject`) is enough to operate the gate.

**Value:** Proposals get long; humans want diffs, edit-before-approve, and one-click
review instead of CLI flags. Lowers the cost of keeping a human at the gate, which is
what makes higher throughput safe.

**v1 seam (already in v1):** the log *is* the state, and every (per-action) verdict goes
through one **`decide(action_id, verdict, edits?)`** function (the CLI is just its first
caller). So the UI is a new front-end on the same function — it reads `pending` actions
from the log and calls `decide()`; it never reimplements the gate. A Slack/API approver
is the same seam.

**Adds later:** read-only inbox + proposal view (S) → edit-before-approve + trace tree
(M) → multi-user, auth, Slack/API approvers (M, pairs with data-governance RBAC).

**Effort:** S (read-only) → M (full review + edit).
