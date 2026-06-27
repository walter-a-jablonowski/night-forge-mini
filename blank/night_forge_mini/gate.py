"""The approval gate + the single `decide()` function (idea_2 guardrail), now
domain-agnostic: it drives the pack's `actions` dict, not any concrete domain.

Auto-run requires `name in allow_list` AND the action is *recoverable*: either
`actions[name].reversible == True`, OR git versioning makes it revertible
(`git_recoverable`, passed in by the caller). This is the HARD FLOOR enforced here in
code — a mis-configured allow-list still cannot auto-run an irreversible action unless
git provides a real undo for it.

Every verdict (auto-run or human) flows through `decide()`, which writes the
`decision`, runs the action (approve/auto only), and writes the `outcome`. A future
UI / Slack / API is just another caller of `decide()`.
"""
from __future__ import annotations

from .pack import Action
from .records import Record, DECISION, OUTCOME
from .store import Store


def can_auto_run(name: str, allow_list: list[str], actions: dict[str, Action],
                 *, git_recoverable: bool = False) -> bool:
    act = actions.get(name)
    if act is None or name not in allow_list:
        return False
    # hard floor: auto-run only what is recoverable — honestly reversible, or made
    # revertible by git versioning (git_recoverable). A misconfigured allow-list still
    # cannot auto-run an irreversible action without a real undo.
    return act.reversible is True or git_recoverable


def decide(store: Store, actions: dict[str, Action], *, domain: str, run_id: str,
           action: dict, verdict: str, by: str, edits: dict | None = None) -> dict:
    """verdict in {auto-run, approve, reject}. Appends decision (+outcome unless reject)."""
    aid = action["action_id"]
    name = action["name"]

    store.append(Record(run_id=run_id, domain=domain, type=DECISION, parent_id=aid,
                         payload={"action_id": aid, "name": name, "verdict": verdict,
                                  "by": by, "edits": edits or None}))

    if verdict == "reject":
        return {"verdict": "reject", "ran": False}

    # idempotency guard: at-most-once per logged outcome (idea_2)
    if aid in store.outcome_action_ids():
        return {"verdict": verdict, "ran": False, "skipped": "outcome already logged"}

    payload = dict(action.get("payload", {}))
    if edits:
        payload.update(edits)

    # Wrap run(): any exception (incl. a missing `target` key) becomes an `error`
    # outcome + stops this branch (idea_2 "Failure handling" — never half-commit).
    act = actions.get(name)
    try:
        if act is None:
            result = {"status": "error", "detail": f"unknown action {name}"}
        else:
            result = act.run(action["target"], payload)
    except Exception as e:  # noqa: BLE001 - last line of defense; reason is logged
        result = {"status": "error", "detail": f"{type(e).__name__}: {e}"}

    store.append(Record(run_id=run_id, domain=domain, type=OUTCOME, parent_id=aid,
                         payload={"action_id": aid, "name": name,
                                  "status": result.get("status", "ok"),
                                  "detail": result.get("detail", "")}))
    return {"verdict": verdict, "ran": True, "result": result}
