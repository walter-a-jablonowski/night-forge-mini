"""Metric `pages`: how many pages (.html/.htm/.php) the site has."""
from __future__ import annotations

KEYS = ["pages"]


def measure(site, *, model, goal) -> dict:
    return {"pages": len(site.pages())}
