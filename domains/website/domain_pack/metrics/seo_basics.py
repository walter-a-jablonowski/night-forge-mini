"""Metric `seo_basics`: pages that have BOTH a non-empty <title> and a non-empty
<meta name="description"> — a concrete, cheaply measured SEO floor.
"""
from __future__ import annotations

import re

KEYS = ["seo_basics"]

_TITLE = re.compile(r"<title[^>]*>\s*([^<]+?)\s*</title>", re.IGNORECASE | re.DOTALL)
# both attribute orders: name= before content= and the reverse
_META_DESC = re.compile(
    r"""<meta\s[^>]*name\s*=\s*["']description["'][^>]*content\s*=\s*["']([^"']+)["']"""
    r"""|<meta\s[^>]*content\s*=\s*["']([^"']+)["'][^>]*name\s*=\s*["']description["']""",
    re.IGNORECASE)


def measure(site, *, model, goal) -> dict:
    ok = 0
    for page in site.pages():
        html = site.read(page)
        m = _META_DESC.search(html)
        desc = (m.group(1) or m.group(2) or "") if m else ""
        if _TITLE.search(html) and desc.strip():
            ok += 1
    return {"seo_basics": ok}
