"""Metric `goal_coverage`: LLM-as-judge — how well the current site covers the
free-text config goal, 0 (not at all) .. 10 (fully). Costs one model call per run.
Under `--fake-llm` it returns a deterministic constant so the offline loop stays
reproducible (the metric-module rule for judge metrics).
"""
from __future__ import annotations

KEYS = ["goal_coverage"]

FAKE_SCORE = 5.0
_BUDGET = 12_000       # total chars of site content shown to the judge
_PER_PAGE = 2_000      # chars per page

SYSTEM = """You judge how well a website currently covers its goal.
Reply with STRICT JSON only: {"score": <number 0-10>, "reason": "<one sentence>"}
0 = not at all, 10 = the goal is fully covered. Judge CONTENT coverage, not styling."""

SCHEMA = {"type": "object",
          "properties": {"score": {"type": "number"}, "reason": {"type": "string"}},
          "required": ["score"]}


def measure(site, *, model, goal) -> dict:
    if model.fake:
        return {"goal_coverage": FAKE_SCORE}
    parts = [f"GOAL: {goal}"]
    used = 0
    for page in site.pages():
        chunk = f"--- {page} ---\n{site.read(page)[:_PER_PAGE]}"
        if used + len(chunk) > _BUDGET:
            break
        parts.append(chunk)
        used += len(chunk)
    result = model.complete_json(SYSTEM, "\n\n".join(parts), schema=SCHEMA)
    score = result.get("score")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise ValueError(f"judge returned no numeric score: {result!r}")
    return {"goal_coverage": max(0.0, min(10.0, float(score)))}
