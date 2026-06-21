"""KB analysis strategy: context -> {finding, metric, actions}.

The pack's analyze owns BOTH the ingest-context (the KB index) AND the metric
measurement for this domain — the blank core just records whatever metric it returns.
Real mode asks the model for a JSON proposal; `--fake-llm` mode is deterministic so the
loop runs offline. Both return the same structure.
"""
from __future__ import annotations

from typing import Any

from night_forge_mini.records import new_id

from .actions import ACTIONS, KnowledgeBase, slug

SYSTEM = """You curate a knowledge base of markdown entries from incoming text snippets.
Goal: {goal}
You may ONLY propose these actions: {actions}.
  add_entry(target=new-entry-id, payload={{title, body, source}})         -- new knowledge (fails if the id already exists)
  edit_entry(target=existing-id, payload={{body}})                        -- rewrite an entry (will require human approval)
  flag_contradiction(target=existing-id, payload={{note}})                -- note a conflict
  mark_stale(target=existing-id)                                          -- mark outdated
Return STRICT JSON only:
{{"finding": "<one sentence>",
  "actions": [{{"name": "...", "target": "...", "rationale": "...", "payload": {{...}}}}]}}
Prefer add_entry for genuinely new information; reuse existing ids (from the index) for edits/flags."""


def analyze(model, *, kb: KnowledgeBase, goal: str, snippets: list[dict],
            recent_findings: list[str]) -> dict[str, Any]:
    kb_index = kb.index()

    if model.fake:
        actions = _fake_actions(kb_index, snippets)
        finding = f"{len(snippets)} new snippet(s); {len(actions)} proposed [fake-llm]"
        model_label = "fake-llm"
    else:
        user = _render_context(goal, kb_index, snippets, recent_findings)
        result = model.complete_json(SYSTEM.format(goal=goal, actions=sorted(ACTIONS)), user)
        actions = _normalize(result.get("actions", []))
        finding = str(result.get("finding") or "")
        model_label = model.label()

    # Metric measured at Analyze (before acting) — this is the pack's job, not the core's.
    metric = {"kb_entries": kb.count(), "stale": kb.stale_count(), "incoming_new": len(snippets)}
    return {"finding": finding, "actions": actions, "metric": metric, "model": model_label}


def _fake_actions(kb_index: list[dict], snippets: list[dict]) -> list[dict]:
    existing = {e["id"] for e in kb_index}
    actions = []
    for s in snippets:
        first = s["text"].splitlines()[0] if s["text"] else s["id"]
        target = slug(first[:48])
        if target in existing:
            # snippet updates a topic already in the KB -> edit_entry (reversible=False),
            # so the gate holds it for approval instead of overwriting curated content.
            actions.append({
                "action_id": new_id("act"),
                "name": "edit_entry",
                "target": target,
                "rationale": "snippet appears to update an existing entry",
                "payload": {"body": s["text"]},
            })
        else:
            actions.append({
                "action_id": new_id("act"),
                "name": "add_entry",
                "target": target,
                "rationale": "new snippet not yet represented in the KB",
                "payload": {"title": first[:80], "body": s["text"], "source": s["source"]},
            })
    return actions


def _normalize(actions: Any) -> list[dict]:
    # Tolerant of malformed model output: a non-list (null / "none" / dict) or any
    # non-dict item becomes nothing, so a bad proposal is an empty action list — not
    # a mid-run crash. _normalize is the sanitizing boundary for model output.
    out = []
    if not isinstance(actions, list):
        return out
    for a in actions:
        if not isinstance(a, dict) or a.get("name") not in ACTIONS:
            continue
        a.setdefault("action_id", new_id("act"))
        a.setdefault("payload", {})
        a.setdefault("rationale", "")
        out.append(a)
    return out


def _render_context(goal: str, kb_index, snippets, recent_findings) -> str:
    idx = "\n".join(f"- {e['id']}: {e['title']} — {e['preview']}" for e in kb_index) or "(empty)"
    snips = "\n\n".join(f"[{s['id']} from {s['source']}]\n{s['text']}" for s in snippets)
    recent = "\n".join(f"- {f}" for f in recent_findings) or "(none)"
    return (f"GOAL: {goal}\n\nCURRENT KB INDEX:\n{idx}\n\n"
            f"RECENT FINDINGS:\n{recent}\n\nNEW SNIPPETS:\n{snips}")
