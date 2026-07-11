"""Website analysis strategy: context -> {finding, metric, actions}.

Agentic (`run_tools`): the model gets the bounded SITE MAP plus READ-ONLY tools —
`read_page` (full source of one site file), plus the core `read_url` (external page as
clean markdown) and `web_search` (research toward the goal) — so it reads on demand
instead of receiving pre-stuffed context. The goal and the brand/CI constraints come
from config and are rendered into the system prompt on EVERY run (soft enforcement,
phase 1). The metric is measured by the config-activated metric modules; `--fake-llm`
mode is deterministic so the whole loop runs offline. Sanitizing the model's action
list is the CORE's job (`sanitize_actions`), not this pack's.
"""
from __future__ import annotations

from typing import Any

from night_forge_mini.pack import proposal_schema
from night_forge_mini.records import new_id
from night_forge_mini.tools import registry
from night_forge_mini.tools.registry import Tool

from . import metrics as metrics_mod
from .actions import ACTIONS
from .site import Site, slug

# Native structured output: name constrained to this pack's actions (core owns the shape).
SCHEMA = proposal_schema(sorted(ACTIONS))

SYSTEM = """You develop and improve a website, file by file.
Goal: {goal}
{constraints}
You may ONLY propose these actions: {actions}.
  create_page(target=relative/path.html, payload={{content}})   -- new page/file (fails if it exists)
  edit_content(target=existing/path.html, payload={{content}})  -- replace an existing file's source
payload.content is ALWAYS the complete file source (HTML/CSS/...), never a fragment or a diff.
Keep the site consistent: link a new page from an existing page (usually index.html) in the
same run, give every page a <title> and a <meta name="description">, keep shared styles working.
Use the tools before proposing: ALWAYS read_page a file before edit_content on it, and base the
new source on what is actually there; use web_search / read_url to research content for the goal.
When you are done reading, return STRICT JSON only (no more tool calls):
{{"finding": "<one sentence>",
  "actions": [{{"name": "...", "target": "...", "rationale": "...", "payload": {{...}}}}]}}
Do NOT re-propose actions the human rejected, and do not repeat actions that recently failed.
Each action may state "expected_impact": the metric change you expect if it runs, using the
metric keys: {metric_keys}. Past predicted-vs-actual results are shown - calibrate against them."""


def analyze(model, *, site: Site, goal: str, constraints: str, snippets: list[dict],
            history: dict[str, list], metric_mods: list, map_max: int = 50,
            tool_steps: int = 8) -> dict[str, Any]:
    site_map = site.site_map()

    if model.fake:
        actions: Any = _fake_actions(site, snippets)
        finding = f"{len(snippets)} new snippet(s); {len(actions)} proposed [fake-llm]"
        model_label = "fake-llm"
    else:
        user = _render_context(goal, site_map[:map_max], snippets, history,
                               total=len(site_map))
        system = SYSTEM.format(goal=goal, constraints=_constraints_block(constraints),
                               actions=sorted(ACTIONS),
                               metric_keys=", ".join(metrics_mod.keys(metric_mods)) or "(none)")
        if tool_steps > 0:  # agentic: model may read pages/sources before proposing
            result = model.run_tools(system, user, tools=_tools(site), schema=SCHEMA,
                                     max_steps=tool_steps)
        else:               # tool_steps 0 = one-shot mode
            result = model.complete_json(system, user, schema=SCHEMA)
        actions = result.get("actions")  # raw model output — the core sanitizes it
        finding = str(result.get("finding") or "")
        model_label = model.label()

    _stamp_edit_base(site, actions)  # stale-edit guard: fingerprint each proposed edit

    # Metric measured at Analyze (before acting) — the config-activated metric modules.
    metric, errors = metrics_mod.measure_all(metric_mods, site, model=model, goal=goal)
    metric["incoming_new"] = len(snippets)
    if errors:
        finding = f"{finding} [metric errors: {'; '.join(errors)}]".strip()
    return {"finding": finding, "actions": actions, "metric": metric, "model": model_label}


def _constraints_block(constraints: str) -> str:
    c = constraints.strip()
    if not c:
        return "No special brand constraints."
    return ("CONSTRAINTS - every change MUST respect these; they override all "
            "improvement ideas:\n" + c)


def _read_page_tool(site: Site) -> Tool:
    """READ-ONLY tool for the agentic loop: the full source of one site file, so the
    model reads what it is about to edit instead of guessing from the map."""
    return Tool(name="read_page",
                description="Read the FULL source of one site file by its relative path "
                            "(see the site map). Always read a file before proposing "
                            "edit_content on it.",
                run=lambda path="": site.read(str(path)),
                params={"type": "object",
                        "properties": {"path": {"type": "string",
                                                "description": "relative site path from the map"}},
                        "required": ["path"]})


def _tools(site: Site) -> list[Tool]:
    """read_page + the core research tools. run_tools drops unavailable ones itself
    (e.g. web_search without a key), so this list is the OFFER, not a guarantee."""
    tools = [_read_page_tool(site)]
    for name in ("read_url", "web_search"):
        t = registry.get(name)
        if t is not None:
            tools.append(t)
    return tools


def _fake_actions(site: Site, snippets: list[dict]) -> list[dict]:
    """Deterministic offline proposals: one page per snippet — create_page for a new
    topic, edit_content when the derived page already exists (exercises both actions
    and the git-recoverable gate path with no model)."""
    actions = []
    for s in snippets:
        first = (s["text"].splitlines()[0] if s["text"] else s["id"])[:48]
        target = f"pages/{slug(first)}.html"
        if site.exists(target):
            actions.append({
                "action_id": new_id("act"),
                "name": "edit_content",
                "target": target,
                "rationale": "snippet appears to update an existing page",
                "payload": {"content": _fake_page(first, s["text"])},
            })
        else:
            actions.append({
                "action_id": new_id("act"),
                "name": "create_page",
                "target": target,
                "rationale": "new content not yet on the site",
                "payload": {"content": _fake_page(first, s["text"])},
                "expected_impact": {"pages": 1},  # exercises predicted-vs-actual offline
            })
    return actions


def _fake_page(title: str, body: str) -> str:
    return ('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<title>{title}</title>\n<meta name="description" content="{title}">\n'
            '<link rel="stylesheet" href="../style.css">\n</head>\n<body>\n<main>\n'
            f'<h1>{title}</h1>\n<pre>{body[:500]}</pre>\n</main>\n</body>\n</html>\n')


def _stamp_edit_base(site: Site, actions: Any) -> None:
    """Record the current content fingerprint on each proposed edit_content, so the
    action can refuse a stale overwrite at approval time (optimistic concurrency).
    Defensive on shape: `actions` is raw model output (the core sanitizes it later)."""
    if not isinstance(actions, list):
        return
    for a in actions:
        if isinstance(a, dict) and a.get("name") == "edit_content" and a.get("target"):
            if not isinstance(a.get("payload"), dict):
                a["payload"] = {}
            a["payload"].setdefault("base", site.fingerprint(str(a["target"])))


def _render_context(goal: str, site_map: list[dict], snippets, history: dict[str, list],
                    total: int | None = None) -> str:
    head = "SITE MAP"
    if total is not None and len(site_map) < total:
        head += f" (first {len(site_map)} of {total} files)"
    rows = "\n".join(f"- {e['path']}: {e['title'] or '(no title)'} ({e['size']} chars)"
                     for e in site_map) or "(empty site)"
    snips = "\n\n".join(f"[{s['id']} from {s['source']}]\n{s['text']}" for s in snippets)
    recent = "\n".join(f"- {f}" for f in history.get("findings", [])) or "(none)"

    parts = [f"GOAL: {goal}", f"{head}:\n{rows}"]
    metrics = history.get("metrics", [])
    if metrics:
        trend = "\n".join("- " + "  ".join(f"{k}={v}" for k, v in m.items()) for m in metrics)
        parts.append(f"METRIC HISTORY (oldest first — are we improving toward the goal?):\n{trend}")
    impact = history.get("impact", [])
    if impact:
        def fmt( d ):
            return "  ".join(f"{k}{v:+g}" for k, v in d.items()) or "(none measurable)"
        rows2 = "\n".join(f"- predicted {fmt(i['predicted'])} -> actual {fmt(i['actual'])}"
                          for i in impact)
        parts.append(f"YOUR PREDICTED vs ACTUAL metric impact (calibrate!):\n{rows2}")
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
    parts.append(f"NEW EXTERNAL CONTENT:\n{snips}")
    return "\n\n".join(parts)
