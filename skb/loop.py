"""The v1 loop: Capture -> Ingest -> Analyze -> Propose -> Gate, plus the
resume paths (approve/reject) that append under the original run_id.
"""
from __future__ import annotations

from typing import Any

from . import analyze as analyze_mod
from .actions import ACTIONS, KnowledgeBase
from .config import Config
from .connector import build as build_connector
from .gate import can_auto_run, decide
from .llm import ModelWrapper
from .records import Record, new_id, now_iso, INPUT, ANALYSIS, PROPOSAL
from .store import Store


class Engine:
    def __init__(self, cfg: Config, fake_llm: bool = False):
        self.cfg = cfg
        self.store = Store(cfg.path("log"))
        self.kb = KnowledgeBase(cfg.path("kb"))
        self.connector = build_connector(cfg.connector, cfg.path("inbox"))
        self.model = ModelWrapper(cfg.provider(), fake=fake_llm)

    # --- run-once ----------------------------------------------------------

    def run_once(self) -> dict[str, Any]:
        domain = self.cfg.domain
        seen = self.store.seen_snippet_ids(self.connector.name)
        snippets = self.connector.fetch(seen)
        if not snippets:
            return {"status": "noop", "reason": "no new snippets"}

        run_id = new_id("run")

        # ① Capture
        self.store.append(Record(run_id=run_id, domain=domain, type=INPUT,
                                 source=self.connector.name,
                                 payload={"connector": self.connector.name,
                                          "snippet_ids": [s["id"] for s in snippets],
                                          "snippets": snippets}))

        # ② Ingest
        kb_index = self.kb.index()
        recent_findings = [r.payload.get("finding", "") for r in self.store.of_type(ANALYSIS)][-self.cfg.recent_runs:]

        # ③ Analyze (measured metric value observed here, before acting)
        start = now_iso()
        result = analyze_mod.analyze(self.model, goal=self.cfg.goal, kb_index=kb_index,
                                     snippets=snippets, recent_findings=recent_findings)
        metric_value = {"kb_entries": self.kb.count(), "stale": self.kb.stale_count(),
                        "incoming_new": len(snippets)}
        self.store.append(Record(run_id=run_id, domain=domain, type=ANALYSIS,
                                 start_ts=start, end_ts=now_iso(),
                                 payload={"finding": result["finding"], "metric": metric_value,
                                          "goal": self.cfg.goal, "model": result["model"]}))

        # ④ Propose
        actions = result["actions"]
        for a in actions:
            a["domain"] = domain
            meta = ACTIONS[a["name"]]
            a.setdefault("risk_level", meta["risk_level"])
            a["reversible"] = meta["reversible"]
        self.store.append(Record(run_id=run_id, domain=domain, type=PROPOSAL,
                                 payload={"actions": actions}))

        # ⑤ Gate (per action)
        ran, pending = [], []
        for a in actions:
            if can_auto_run(a["name"], self.cfg.allow_list):
                res = decide(self.store, self.kb, run_id=run_id, action=a,
                             verdict="auto-run", by="allow-list")
                ran.append({"action": a, "res": res})
            else:
                pending.append(a)

        return {"status": "ok", "run_id": run_id, "captured": len(snippets),
                "finding": result["finding"], "metric": metric_value,
                "model": result["model"], "ran": ran, "pending": pending}

    # --- resume (approve / reject) ----------------------------------------

    def _locate(self, action_id: str) -> dict | None:
        return self.store.proposed_actions().get(action_id)

    def approve(self, action_id: str, by: str = "user", edits: dict | None = None) -> dict[str, Any]:
        loc = self._locate(action_id)
        if not loc:
            return {"status": "error", "reason": f"no proposed action {action_id}"}
        if action_id in self.store.decided_action_ids():
            return {"status": "error", "reason": f"{action_id} already decided"}
        res = decide(self.store, self.kb, run_id=loc["run_id"], action=loc["action"],
                     verdict="approve", by=by, edits=edits)
        return {"status": "ok", "run_id": loc["run_id"], "action": loc["action"], "res": res}

    def reject(self, action_id: str, by: str = "user") -> dict[str, Any]:
        loc = self._locate(action_id)
        if not loc:
            return {"status": "error", "reason": f"no proposed action {action_id}"}
        if action_id in self.store.decided_action_ids():
            return {"status": "error", "reason": f"{action_id} already decided"}
        res = decide(self.store, self.kb, run_id=loc["run_id"], action=loc["action"],
                     verdict="reject", by=by)
        return {"status": "ok", "run_id": loc["run_id"], "action": loc["action"], "res": res}
