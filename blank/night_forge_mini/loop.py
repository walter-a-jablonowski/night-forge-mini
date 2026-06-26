"""The v1 loop: Capture -> Ingest -> Analyze -> Propose -> Gate, plus the resume
paths (approve/reject) that append under the original run_id.

Domain-agnostic: the Engine is handed a `Pack` (connector, goal, analyze, actions).
The pack measures its own metric inside `analyze` and returns it; the core just records
whatever metric the pack hands back.
"""
from __future__ import annotations

from typing import Any

from .gate import can_auto_run, decide
from .git_sync import Git
from .llm import ModelWrapper
from .pack import Pack
from .records import Record, new_id, now_iso, INPUT, ANALYSIS, PROPOSAL
from .store import Store


class Engine:
    def __init__(self, cfg, pack: Pack, fake_llm: bool = False):
        self.cfg = cfg
        self.pack = pack
        self.store = Store(cfg.path("log"))
        self.model = ModelWrapper(cfg.provider(), fake=fake_llm)
        self.git = Git.from_config(cfg)

    # --- run-once ----------------------------------------------------------

    def run_once(self) -> dict[str, Any]:
        domain = self.pack.domain
        connector = self.pack.connector
        seen = self.store.seen_snippet_ids(connector.name)
        snippets = connector.fetch(seen)
        if not snippets:
            return {"status": "noop", "reason": "no new snippets"}

        run_id = new_id("run")

        # (1) Capture
        self.store.append(Record(run_id=run_id, domain=domain, type=INPUT,
                                 source=connector.name,
                                 payload={"connector": connector.name,
                                          "snippet_ids": [s["id"] for s in snippets],
                                          "snippets": snippets}))

        # (2) Ingest (generic history) + (3) Analyze (pack builds context + measures metric)
        recent_findings = [r.payload.get("finding", "") for r in self.store.of_type(ANALYSIS)][-self.cfg.recent_runs:]
        start = now_iso()
        result = self.pack.analyze(self.model, goal=self.pack.goal,
                                   snippets=snippets, recent_findings=recent_findings)
        metric_value = result.get("metric", {})
        self.store.append(Record(run_id=run_id, domain=domain, type=ANALYSIS,
                                 start_ts=start, end_ts=now_iso(),
                                 payload={"finding": result["finding"], "metric": metric_value,
                                          "goal": self.pack.goal, "model": result.get("model", "")}))

        # (4) Propose — tag each action with the pack's honest risk_level + reversible
        actions = result["actions"]
        for a in actions:
            a["domain"] = domain
            act = self.pack.actions.get(a["name"])
            if act is not None:
                a.setdefault("risk_level", act.risk_level)
                a["reversible"] = act.reversible
        self.store.append(Record(run_id=run_id, domain=domain, type=PROPOSAL,
                                 payload={"actions": actions}))

        # (5) Gate (per action)
        ran, pending, git_results = [], [], []
        for a in actions:
            if can_auto_run(a["name"], self.cfg.allow_list, self.pack.actions):
                res = decide(self.store, self.pack.actions, domain=domain, run_id=run_id,
                             action=a, verdict="auto-run", by="allow-list")
                ran.append({"action": a, "res": res})
                # (6) Version the materialized artifacts (per-action granularity).
                gr = self._commit_action(run_id, a, res)
                if gr:
                    git_results.append(gr)
            else:
                pending.append(a)

        gr = self._commit_run(run_id, ran)  # per-run granularity: one commit for the pass
        if gr:
            git_results.append(gr)

        return {"status": "ok", "run_id": run_id, "captured": len(snippets),
                "finding": result["finding"], "metric": metric_value,
                "model": result.get("model", ""), "ran": ran, "pending": pending,
                "git": git_results}

    # --- git versioning of the materialized artifacts ----------------------

    @staticmethod
    def _ran_ok(res: dict) -> bool:
        return bool(res.get("ran")) and res.get("result", {}).get("status", "ok") == "ok"

    def _commit_msg(self, run_id: str, action: dict) -> str:
        target = action.get("target", "")
        return f"{run_id}: {action['name']} {target} [{action['action_id']}]".replace("  ", " ").strip()

    def _commit_action(self, run_id: str, action: dict, res: dict) -> dict | None:
        if self.git.granularity != "per_action" or not self._ran_ok(res):
            return None
        return self.git.commit(self._commit_msg(run_id, action))

    def _commit_run(self, run_id: str, ran: list[dict]) -> dict | None:
        if self.git.granularity != "per_run":
            return None
        n = sum(1 for item in ran if self._ran_ok(item["res"]))
        if n == 0:
            return None
        return self.git.commit(f"{run_id}: {n} action(s) auto-run")

    def _commit_resume(self, run_id: str, action: dict, res: dict) -> dict | None:
        # A single approved/held action is its own unit of work -> commit on success
        # regardless of granularity.
        if not self._ran_ok(res):
            return None
        return self.git.commit(self._commit_msg(run_id, action))

    # --- resume (approve / reject) ----------------------------------------

    def _locate(self, action_id: str) -> dict | None:
        return self.store.proposed_actions().get(action_id)

    def _resume(self, action_id: str, verdict: str, by: str, edits: dict | None = None) -> dict[str, Any]:
        loc = self._locate(action_id)
        if not loc:
            return {"status": "error", "reason": f"no proposed action {action_id}"}
        if action_id in self.store.decided_action_ids():
            return {"status": "error", "reason": f"{action_id} already decided"}
        action = loc["action"]
        res = decide(self.store, self.pack.actions, domain=action.get("domain", self.pack.domain),
                     run_id=loc["run_id"], action=action, verdict=verdict, by=by, edits=edits)
        git_res = self._commit_resume(loc["run_id"], action, res)
        return {"status": "ok", "run_id": loc["run_id"], "action": action, "res": res,
                "git": git_res}

    def approve(self, action_id: str, by: str = "user", edits: dict | None = None) -> dict[str, Any]:
        return self._resume(action_id, "approve", by, edits)

    def reject(self, action_id: str, by: str = "user") -> dict[str, Any]:
        return self._resume(action_id, "reject", by)
