"""The approval gate + the single `decide()` function (idea_2 guardrail).

Auto-run requires BOTH `name in allow_list` AND `reversible == true`.
The `reversible == false` block is a HARD FLOOR enforced here in code — a
mis-configured allow-list still cannot auto-run an irreversible action.

Every verdict (auto-run or human) flows through `decide()`, which writes the
`decision`, runs the action (approve/auto only), and writes the `outcome`. A future
UI / Slack / API is just another caller of `decide()`.
"""
from __future__ import annotations

from .actions import ACTIONS, KnowledgeBase
from .records import Record, DECISION, OUTCOME
from .store import Store


def can_auto_run(name: str, allow_list: list[str]) -> bool:
    meta = ACTIONS.get(name)
    if not meta:
        return False
    return name in allow_list and meta["reversible"] is True  # hard floor on reversible


def decide(store: Store, kb: KnowledgeBase, *, run_id: str, action: dict,
           verdict: str, by: str, edits: dict | None = None) -> dict:
    """verdict in {auto-run, approve, reject}. Appends decision (+outcome unless reject)."""
    aid = action["action_id"]
    name = action["name"]

    store.append(Record(run_id=run_id, domain=kb_domain(action), type=DECISION,
                         parent_id=aid,
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
    result = kb.run(name, action["target"], payload)

    store.append(Record(run_id=run_id, domain=kb_domain(action), type=OUTCOME,
                         parent_id=aid,
                         payload={"action_id": aid, "name": name,
                                  "status": result.get("status", "ok"),
                                  "detail": result.get("detail", "")}))
    return {"verdict": verdict, "ran": True, "result": result}


def kb_domain(action: dict) -> str:
    # domain is a constant in v1; carried for forward-compat (per-domain attribution).
    return action.get("domain", "knowledge-base")
