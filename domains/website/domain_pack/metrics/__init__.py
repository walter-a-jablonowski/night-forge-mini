"""Pluggable metric modules (interface decided 2026-07-11, see
tasks/backlog/website-domain-pack.md "Metric modules — interface").

One module per metric under `domain_pack/metrics/`, exposing exactly two things:

    KEYS = ["seo_basics"]                          # metric keys it produces
    def measure(site, *, model, goal) -> dict      # e.g. {"seo_basics": 7}

Built-ins are wired explicitly below (the tools/__init__ pattern, no import-time
magic); an unknown config name falls back to `importlib.import_module`, so a custom
metric for an installation is just a dropped-in `metrics/<name>.py` plus its name in
config — no code edits. A module that raises at measure time is skipped (its keys are
omitted, the error reported); a broken metric must never kill the run. A judge-style
metric MUST return a deterministic constant under `--fake-llm` (`model.fake`).
"""
from __future__ import annotations

import importlib
from typing import Any

from . import broken_links, goal_coverage, pages, seo_basics

BUILTINS = {
    "pages": pages,
    "broken_links": broken_links,
    "seo_basics": seo_basics,
    "goal_coverage": goal_coverage,
}


def load(names: list[str]) -> list:
    """Resolve config's `metrics` names to modules. Unknown names are operator
    drop-ins (`domain_pack/metrics/<name>.py`); a bad name fails fast at build time."""
    mods = []
    for name in names:
        mod = BUILTINS.get(str(name))
        if mod is None:
            mod = importlib.import_module(f"{__name__}.{name}")
        mods.append(mod)
    return mods


def keys(mods: list) -> list[str]:
    """Union of the active modules' metric keys — what expected_impact may predict."""
    out: list[str] = []
    for mod in mods:
        out.extend(getattr(mod, "KEYS", []))
    return out


def measure_all(mods: list, site, *, model, goal: str) -> tuple[dict[str, Any], list[str]]:
    """Merged metric across the active modules. Failure isolation: a raising module is
    skipped and reported in the second return value, never propagated."""
    metric: dict[str, Any] = {}
    errors: list[str] = []
    for mod in mods:
        name = mod.__name__.rsplit(".", 1)[-1]
        try:
            metric.update(mod.measure(site, model=model, goal=goal))
        except Exception as e:  # noqa: BLE001 - a broken metric must never kill the run
            errors.append(f"{name}: {type(e).__name__}: {e}")
    return metric, errors
