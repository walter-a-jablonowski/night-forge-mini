"""KB analysis strategy: context -> {finding, metric, actions}.

The pack's analyze owns BOTH the ingest-context (the KB index) AND the metric
measurement for this domain — the blank core just records whatever metric it returns.
Real mode asks the model for a JSON proposal; `--fake-llm` mode is deterministic so the
loop runs offline. Both return the same structure. Sanitizing the model's action list
is the CORE's job (`sanitize_actions` in night_forge_mini.pack), not this pack's —
this module only has to survive raw output long enough to hand it back.

Bounded context (idea_2 "never the full store"): the model sees only a **relevant slice**
of the KB — the top `context_max` entries by keyword overlap with the incoming snippets —
so context size is capped no matter how large the KB grows. The `history` the core hands
in (findings, metric trend, human rejections, failed actions) is already bounded by
`recent_runs` and closes the loop: the model is told what was rejected and what failed.
"""
from __future__ import annotations

import re
from typing import Any

from night_forge_mini.pack import proposal_schema
from night_forge_mini.records import new_id
from night_forge_mini.tools.registry import Tool

from .actions import ACTIONS, KnowledgeBase, slug

# Native structured output: name constrained to this pack's actions (core owns the shape).
SCHEMA = proposal_schema(sorted(ACTIONS))


def _read_entry_tool(kb: KnowledgeBase) -> Tool:
    """READ-ONLY tool for the agentic loop: the full markdown of one KB entry, so the
    model reads what it is about to edit instead of guessing from a 120-char preview."""
    return Tool(name="read_entry",
                description="Read the FULL markdown of one KB entry by its id (see the "
                            "index). Always read an entry before proposing edit_entry on it.",
                run=lambda id="": kb.read(str(id)),
                params={"type": "object",
                        "properties": {"id": {"type": "string",
                                              "description": "entry id from the KB index"}},
                        "required": ["id"]})

SYSTEM = """You curate a knowledge base of markdown entries from incoming text snippets.
Goal: {goal}
You may ONLY propose these actions: {actions}.
  add_entry(target=new-entry-id, payload={{title, body, source}})         -- new knowledge (fails if the id already exists)
  edit_entry(target=existing-id, payload={{body}})                        -- rewrite an entry (will require human approval)
  flag_contradiction(target=existing-id, payload={{note}})                -- note a conflict
  mark_stale(target=existing-id)                                          -- mark outdated
You can call the read_entry tool to read any entry in full - ALWAYS read an entry before
proposing edit_entry on it, and base the new body on what is actually there.
When you are done reading, return STRICT JSON only (no more tool calls):
{{"finding": "<one sentence>",
  "actions": [{{"name": "...", "target": "...", "rationale": "...", "payload": {{...}}}}]}}
Prefer add_entry for genuinely new information; reuse existing ids (from the index) for edits/flags.
Do NOT re-propose actions the human rejected, and do not repeat actions that recently failed."""


def analyze(model, *, kb: KnowledgeBase, goal: str, snippets: list[dict],
            history: dict[str, list], context_max: int = 20,
            tool_steps: int = 6) -> dict[str, Any]:
    kb_index = kb.index()

    if model.fake:
        # fake routing needs the full id set (add vs edit), not a slice — no model, no token budget.
        actions: Any = _fake_actions(kb_index, snippets)
        finding = f"{len(snippets)} new snippet(s); {len(actions)} proposed [fake-llm]"
        model_label = "fake-llm"
    else:
        context_index = _relevant_slice(kb_index, snippets, context_max)
        user = _render_context(goal, context_index, snippets, history, total=len(kb_index))
        system = SYSTEM.format(goal=goal, actions=sorted(ACTIONS))
        if tool_steps > 0:  # agentic: model may read entries in full before proposing
            result = model.run_tools(system, user, tools=[_read_entry_tool(kb)],
                                     schema=SCHEMA, max_steps=tool_steps)
        else:               # tool_steps 0 = one-shot mode
            result = model.complete_json(system, user, schema=SCHEMA)
        actions = result.get("actions")  # raw model output — the core sanitizes it
        finding = str(result.get("finding") or "")
        model_label = model.label()

    _stamp_edit_base(kb, actions)  # stale-edit guard: fingerprint each proposed edit_entry

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


def _stamp_edit_base(kb: KnowledgeBase, actions: Any) -> None:
    """Record the current body fingerprint on each proposed edit_entry, so `edit_entry` can
    refuse a stale overwrite at approval time (optimistic concurrency). See stale-edit-guard.
    Defensive on shape: `actions` is raw model output here (the core sanitizes it later)."""
    if not isinstance(actions, list):
        return
    for a in actions:
        if isinstance(a, dict) and a.get("name") == "edit_entry" and a.get("target"):
            if not isinstance(a.get("payload"), dict):
                a["payload"] = {}
            a["payload"].setdefault("base", kb.fingerprint(str(a["target"])))


_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if len(t) >= 3}


def _relevant_slice(kb_index: list[dict], snippets: list[dict], limit: int) -> list[dict]:
    """Bounded context: the top `limit` KB entries by keyword overlap with the incoming
    snippets, so context size is capped regardless of KB size (idea_2 "never the full
    store"). Under the cap (or limit <= 0), returns the whole index."""
    if limit <= 0 or len(kb_index) <= limit:
        return kb_index
    q = _tokens(" ".join(s.get("text", "") for s in snippets))
    ranked = sorted(kb_index, key=lambda e: len(q & _tokens(f"{e['title']} {e['preview']}")),
                    reverse=True)  # stable: ties keep index() order
    return ranked[:limit]


def _render_context(goal: str, kb_index, snippets, history: dict[str, list],
                    total: int | None = None) -> str:
    head = "CURRENT KB INDEX"
    if total is not None and len(kb_index) < total:
        head += f" (relevant slice: {len(kb_index)} of {total})"
    idx = "\n".join(f"- {e['id']}: {e['title']} — {e['preview']}" for e in kb_index) or "(empty)"
    snips = "\n\n".join(f"[{s['id']} from {s['source']}]\n{s['text']}" for s in snippets)
    recent = "\n".join(f"- {f}" for f in history.get("findings", [])) or "(none)"

    parts = [f"GOAL: {goal}", f"{head}:\n{idx}"]
    metrics = history.get("metrics", [])
    if metrics:
        trend = "\n".join("- " + "  ".join(f"{k}={v}" for k, v in m.items()) for m in metrics)
        parts.append(f"METRIC HISTORY (oldest first — are we improving toward the goal?):\n{trend}")
    parts.append(f"RECENT FINDINGS:\n{recent}")
    rejections = history.get("rejections", [])
    if rejections:
        rej = "\n".join(f"- {r['name']} {r['target']} — was proposed because: {r['rationale']}"
                        for r in rejections)
        parts.append(f"REJECTED BY THE HUMAN (do NOT re-propose these):\n{rej}")
    failures = history.get("failures", [])
    if failures:
        fail = "\n".join(f"- {f['name']} {f['target']} — failed: {f['detail']}" for f in failures)
        parts.append(f"RECENTLY FAILED ACTIONS (fix the cause or avoid):\n{fail}")
    parts.append(f"NEW SNIPPETS:\n{snips}")
    return "\n\n".join(parts)
