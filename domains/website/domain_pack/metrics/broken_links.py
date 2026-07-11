"""Metric `broken_links`: INTERNAL references (href/src to a local path) pointing at a
file that does not exist in the site. External http(s)/mailto/anchor references are out
of scope — a code metric does no network I/O. Counts references, not distinct targets.
"""
from __future__ import annotations

import posixpath
import re
from urllib.parse import urlparse

KEYS = ["broken_links"]

_REF = re.compile(r"""(?:href|src)\s*=\s*["']([^"'#]+)""", re.IGNORECASE)


def measure(site, *, model, goal) -> dict:
    broken = 0
    for page in site.pages():
        folder = posixpath.dirname(page)
        for ref in _REF.findall(site.read(page)):
            ref = ref.split("?")[0].strip()
            if not ref or urlparse(ref).scheme or ref.startswith("//"):
                continue  # external / mailto / protocol-relative
            if ref.startswith("/"):
                path = ref.lstrip("/")  # site-absolute -> from the site root
            else:
                path = posixpath.normpath(posixpath.join(folder, ref))
            if path.startswith("..") or not site.has_file(path):
                broken += 1
    return {"broken_links": broken}
